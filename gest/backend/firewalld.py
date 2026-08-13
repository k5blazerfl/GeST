"""GeST root D-Bus interface for the firewalld firewall module.

Registered on the shared bus name at /org/gentoo/gest/Firewalld. A single
method, ``ApplyChanges``, takes a staged diff of the default (or any) zone's
allowances — services and ``port/proto`` entries to add and remove — validates
each token server-side (never trusting caller input), applies them with
``firewall-cmd --permanent`` and then ``--reload`` so the permanent config takes
effect live. polkit-gated with org.gentoo.gest.firewalld.manage; audit-logged.

Unlike the nftables module this is a live-system, day-2 module: there is no
target-root seam (firewalld isn't part of the install-target flow), so no
``root`` argument.
"""

from __future__ import annotations

import shutil
import subprocess

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.audit import audit
from gest.backend.polkit import caller_uid, check_authorization
from gest.core.firewalld import commands
from gest.ipc.interface import FIREWALLD_IFACE, FIREWALLD_PATH, FIREWALLD_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{FIREWALLD_IFACE}">
    <method name="ApplyChanges">
      <arg type="s" name="zone" direction="in"/>
      <arg type="as" name="add_services" direction="in"/>
      <arg type="as" name="remove_services" direction="in"/>
      <arg type="as" name="add_ports" direction="in"/>
      <arg type="as" name="remove_ports" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_FIREWALL_CMD = shutil.which("firewall-cmd") or "/usr/bin/firewall-cmd"


def _run(argv: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip()


class FirewalldService:
    """Implements the ``org.gentoo.gest.Firewalld`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            FIREWALLD_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method != "ApplyChanges":
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, FIREWALLD_POLKIT):
            audit(method, uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to change the firewall")
            return
        try:
            zone, add_services, remove_services, add_ports, remove_ports = params.unpack()
            ok, out = self._apply_changes(
                zone, add_services, remove_services, add_ports, remove_ports)
            detail = (f"zone={zone} +svc={list(add_services)} -svc={list(remove_services)} "
                      f"+port={list(add_ports)} -port={list(remove_ports)}")
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        audit(method, uid=uid, result="ok" if ok else "failed", detail=detail)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))

    def _apply_changes(self, zone, add_services, remove_services, add_ports, remove_ports):
        if not commands.valid_zone(zone):
            raise ValueError(f"invalid zone: {zone!r}")
        for service in (*add_services, *remove_services):
            if not commands.valid_service(service):
                raise ValueError(f"invalid service name: {service!r}")
        for port in (*add_ports, *remove_ports):
            if not commands.valid_port(port):
                raise ValueError(f"invalid port (expected N/tcp or N/udp): {port!r}")

        # Apply removals before additions, then reload so the permanent config
        # takes effect on the live runtime.
        steps: list[list[str]] = []
        steps += [commands.remove_service_argv(zone, s, firewall_cmd=_FIREWALL_CMD)
                  for s in remove_services]
        steps += [commands.add_service_argv(zone, s, firewall_cmd=_FIREWALL_CMD)
                  for s in add_services]
        steps += [commands.remove_port_argv(zone, p, firewall_cmd=_FIREWALL_CMD)
                  for p in remove_ports]
        steps += [commands.add_port_argv(zone, p, firewall_cmd=_FIREWALL_CMD)
                  for p in add_ports]

        ok_all = True
        outputs: list[str] = []
        for argv in steps:
            ok, out = _run(argv)
            ok_all = ok_all and ok
            if out:
                outputs.append(out)
        # Even with no permanent changes staged this reload is harmless; but the
        # frontend never calls with an empty diff.
        ok, out = _run(commands.reload_argv(firewall_cmd=_FIREWALL_CMD))
        ok_all = ok_all and ok
        outputs.append(out or "reloaded firewalld")
        summary = "\n".join(outputs).strip() or ("changes applied" if ok_all else "failed")
        return ok_all, summary
