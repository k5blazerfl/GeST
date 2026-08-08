"""GeST root D-Bus interface for the eselect module.

Registered at /org/gentoo/gest/Eselect. Switches an eselect target
(`eselect <module> set <n>`); polkit-gated with org.gentoo.gest.eselect.manage
and audit-logged. Validated argv comes from gest.core.eselect.commands.
"""

from __future__ import annotations

import shutil
import subprocess

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.audit import audit
from gest.backend.polkit import caller_uid, check_authorization
from gest.core.eselect import commands
from gest.ipc.interface import ESELECT_IFACE, ESELECT_PATH, ESELECT_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{ESELECT_IFACE}">
    <method name="SetTarget">
      <arg type="s" name="module" direction="in"/>
      <arg type="s" name="target" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_ESELECT = shutil.which("eselect") or "/usr/bin/eselect"


def _run(argv: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip()


class EselectService:
    """Implements the ``org.gentoo.gest.Eselect`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            ESELECT_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method != "SetTarget":
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, ESELECT_POLKIT):
            audit("SetTarget", uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to change eselect selections")
            return
        try:
            module, target = params.unpack()
            argv = commands.set_argv(module, target, eselect=_ESELECT)
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        ok, out = _run(argv)
        audit("SetTarget", uid=uid, result="ok" if ok else "failed",
              detail=f"{module} {target}")
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))
