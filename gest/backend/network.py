"""GeST root D-Bus interface for the network module.

Registered on the shared bus name at /org/gentoo/gest/Network. Brings interfaces
up/down with `ip link` (universal, independent of netifrc/NetworkManager).
polkit-gated with org.gentoo.gest.network.manage; every action is audit-logged.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.audit import audit
from gest.backend.polkit import caller_uid, check_authorization
from gest.core.network import commands, netifrc
from gest.core.network import hosts as hosts_core
from gest.core.network import resolv as resolv_core
from gest.ipc.interface import NETWORK_IFACE, NETWORK_PATH, NETWORK_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{NETWORK_IFACE}">
    <method name="SetLink">
      <arg type="s" name="iface" direction="in"/>
      <arg type="b" name="up" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="SetInterfaceConfig">
      <arg type="s" name="iface" direction="in"/>
      <arg type="s" name="method" direction="in"/>
      <arg type="s" name="address" direction="in"/>
      <arg type="s" name="gateway" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="SetResolvers">
      <arg type="as" name="nameservers" direction="in"/>
      <arg type="as" name="search" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="SetHosts">
      <arg type="a(sas)" name="entries" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_IP = shutil.which("ip") or "/bin/ip"


def _run(argv: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip()


def _atomic_write(path: str, text: str) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".gest.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class NetworkService:
    """Implements the ``org.gentoo.gest.Network`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            NETWORK_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method not in ("SetLink", "SetInterfaceConfig", "SetResolvers", "SetHosts"):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, NETWORK_POLKIT):
            audit(method, uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to manage network interfaces")
            return
        try:
            if method == "SetLink":
                name, up = params.unpack()
                ok, out = _run(commands.iplink_argv(name, up, ip=_IP))
                detail = f"{name} {'up' if up else 'down'}"
            elif method == "SetInterfaceConfig":
                name, cfg_method, address, gateway = params.unpack()
                ok, out = self._set_interface_config(name, cfg_method, address, gateway)
                detail = f"{name} {cfg_method}"
            elif method == "SetResolvers":
                nameservers, search = params.unpack()
                ok, out = self._set_resolvers(list(nameservers), list(search))
                detail = f"{len(nameservers)} nameservers"
            else:  # SetHosts
                (entries,) = params.unpack()
                ok, out = self._set_hosts(entries)
                detail = f"{len(entries)} host entries"
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        except OSError as exc:
            invocation.return_value(GLib.Variant("(bs)", (False, f"write failed: {exc}")))
            return
        audit(method, uid=uid, result="ok" if ok else "failed", detail=detail)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))

    def _set_interface_config(self, iface, method, address, gateway):
        if not commands.valid_iface(iface):
            raise ValueError("invalid interface")
        if method not in ("dhcp", "static", "none"):
            raise ValueError("invalid method")
        if method == "static":
            if not netifrc.valid_address(address):
                raise ValueError("invalid IP address (need CIDR, e.g. 192.168.1.5/24)")
            if not netifrc.valid_gateway(gateway):
                raise ValueError("invalid gateway address")
        path = "/etc/conf.d/net"
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            text = ""
        cfg = netifrc.InterfaceConfig(
            iface, method,
            address if method == "static" else "",
            gateway if method == "static" else "",
        )
        _atomic_write(path, netifrc.render_conf_net(text, cfg))
        return True, f"{iface} configured as {method} (restart net.{iface} to apply)"

    def _set_resolvers(self, nameservers, search):
        if not resolv_core.valid_resolv(nameservers, search):
            raise ValueError("need at least one valid nameserver; check the search domains")
        _atomic_write("/etc/resolv.conf", resolv_core.render_resolv(nameservers, search))
        return True, f"resolv.conf updated ({len(nameservers)} nameserver(s))"

    def _set_hosts(self, entries):
        parsed = [hosts_core.HostsEntry(address, list(names)) for address, names in entries]
        if not hosts_core.valid_hosts(parsed):
            raise ValueError("invalid host entries (need a valid IP and hostname on each)")
        _atomic_write("/etc/hosts", hosts_core.render_hosts(parsed))
        return True, f"/etc/hosts updated ({len(parsed)} entr{'y' if len(parsed) == 1 else 'ies'})"
