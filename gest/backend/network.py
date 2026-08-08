"""GeST root D-Bus interface for the network module.

Registered on the shared bus name at /org/gentoo/gest/Network. Brings interfaces
up/down with `ip link` (universal, independent of netifrc/NetworkManager).
polkit-gated with org.gentoo.gest.network.manage; every action is audit-logged.
"""

from __future__ import annotations

import shutil
import subprocess

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.audit import audit
from gest.backend.polkit import caller_uid, check_authorization
from gest.core.network import commands
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
  </interface>
</node>
"""

_IP = shutil.which("ip") or "/bin/ip"


def _run(argv: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip()


class NetworkService:
    """Implements the ``org.gentoo.gest.Network`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            NETWORK_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method != "SetLink":
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, NETWORK_POLKIT):
            audit("SetLink", uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to manage network interfaces")
            return
        try:
            name, up = params.unpack()
            argv = commands.iplink_argv(name, up, ip=_IP)
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        ok, out = _run(argv)
        audit("SetLink", uid=uid, result="ok" if ok else "failed",
              detail=f"{name} {'up' if up else 'down'}")
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))
