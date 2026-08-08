"""GeST root D-Bus interface for the bootloader & kernel module.

Registered at /org/gentoo/gest/Bootloader. Regenerates the bootloader config
(`grub-mkconfig -o …`); polkit-gated with org.gentoo.gest.bootloader.manage and
audit-logged.
"""

from __future__ import annotations

import shutil
import subprocess

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.audit import audit
from gest.backend.polkit import caller_uid, check_authorization
from gest.core.bootloader import commands
from gest.ipc.interface import BOOTLOADER_IFACE, BOOTLOADER_PATH, BOOTLOADER_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{BOOTLOADER_IFACE}">
    <method name="RegenerateGrub">
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_GRUB_MKCONFIG = shutil.which("grub-mkconfig") or "/usr/sbin/grub-mkconfig"


class BootloaderService:
    """Implements the ``org.gentoo.gest.Bootloader`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            BOOTLOADER_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method != "RegenerateGrub":
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, BOOTLOADER_POLKIT):
            audit("RegenerateGrub", uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to regenerate the bootloader config")
            return
        argv = commands.grub_mkconfig_argv(grub_mkconfig=_GRUB_MKCONFIG)
        proc = subprocess.run(argv, capture_output=True, text=True)
        out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
        ok = proc.returncode == 0
        audit("RegenerateGrub", uid=uid, result="ok" if ok else "failed")
        invocation.return_value(GLib.Variant("(bs)", (ok, out.strip())))
