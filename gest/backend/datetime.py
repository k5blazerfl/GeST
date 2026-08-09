"""GeST root D-Bus interface for the date & time module.

Registered on the shared bus name at /org/gentoo/gest/DateTime. Sets the system
clock (`date -s`) and syncs it to the hardware clock (`hwclock --systohc`).
polkit-gated with org.gentoo.gest.datetime.manage; every action is audit-logged.
Enabling an NTP daemon is not done here — it's an OpenRC service, handled through
the Services backend.
"""

from __future__ import annotations

import shutil
import subprocess

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.audit import audit
from gest.backend.polkit import caller_uid, check_authorization
from gest.core.datetime import commands
from gest.ipc.interface import DATETIME_IFACE, DATETIME_PATH, DATETIME_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{DATETIME_IFACE}">
    <method name="SetClock">
      <arg type="s" name="timestamp" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_DATE = shutil.which("date") or "/bin/date"
_HWCLOCK = shutil.which("hwclock") or "/sbin/hwclock"


def _run(argv: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip()


class DateTimeService:
    """Implements the ``org.gentoo.gest.DateTime`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            DATETIME_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method != "SetClock":
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, DATETIME_POLKIT):
            audit(method, uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to set the system clock")
            return
        try:
            (timestamp,) = params.unpack()
            argv = commands.set_clock_argv(timestamp, date=_DATE)
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        ok, out = _run(argv)
        if ok:
            # Persist to the hardware clock; non-fatal if it fails (e.g. no RTC).
            hc_ok, hc_out = _run([_HWCLOCK, "--systohc"])
            if not hc_ok:
                out = f"{out}\n(clock set; hwclock --systohc failed: {hc_out})".strip()
        audit(method, uid=uid, result="ok" if ok else "failed", detail=timestamp)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))
