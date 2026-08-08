"""GeST root D-Bus interface for the repositories module.

Registered at /org/gentoo/gest/Repos. Enables/disables/removes/adds Portage
repositories via `eselect repository`. Reuses the software.modify-config polkit
action (repositories are Portage config); audit-logged.
"""

from __future__ import annotations

import shutil
import subprocess

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.audit import audit
from gest.backend.polkit import caller_uid, check_authorization
from gest.core.repos import commands
from gest.ipc.interface import REPOS_IFACE, REPOS_PATH, polkit_action

_INTROSPECTION = f"""
<node>
  <interface name="{REPOS_IFACE}">
    <method name="Enable">
      <arg type="s" name="name" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="Disable">
      <arg type="s" name="name" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="Remove">
      <arg type="s" name="name" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="Add">
      <arg type="s" name="name" direction="in"/>
      <arg type="s" name="sync_type" direction="in"/>
      <arg type="s" name="uri" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_ESELECT = shutil.which("eselect") or "/usr/bin/eselect"
_POLKIT = polkit_action("modify-config")


def _run(argv: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip()


class ReposService:
    """Implements the ``org.gentoo.gest.Repos`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            REPOS_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        builders = {
            "Enable": lambda a: commands.enable_argv(a[0], eselect=_ESELECT),
            "Disable": lambda a: commands.disable_argv(a[0], eselect=_ESELECT),
            "Remove": lambda a: commands.remove_argv(a[0], eselect=_ESELECT),
            "Add": lambda a: commands.add_argv(a[0], a[1], a[2], eselect=_ESELECT),
        }
        if method not in builders:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, _POLKIT):
            audit(f"repo.{method}", uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to manage repositories")
            return
        try:
            argv = builders[method](params.unpack())
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        ok, out = _run(argv)
        audit(f"repo.{method}", uid=uid, result="ok" if ok else "failed",
              detail=params.unpack()[0])
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))
