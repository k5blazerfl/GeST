"""GeST root D-Bus interface for the bootloader & kernel module.

Registered at /org/gentoo/gest/Bootloader. Regenerates the bootloader config
(`grub-mkconfig -o …`, gated by org.gentoo.gest.bootloader.manage) and installs
GRUB (`grub-install`, UEFI or BIOS, gated by the more-impactful
org.gentoo.gest.bootloader.install). Every action is audit-logged; the install
argv is re-validated server-side via the shared command builder.
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
from gest.ipc.interface import (
    BOOTLOADER_IFACE,
    BOOTLOADER_INSTALL_POLKIT,
    BOOTLOADER_PATH,
    BOOTLOADER_POLKIT,
)

_INTROSPECTION = f"""
<node>
  <interface name="{BOOTLOADER_IFACE}">
    <method name="RegenerateGrub">
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="InstallGrub">
      <arg type="s" name="firmware" direction="in"/>
      <arg type="s" name="efi_directory" direction="in"/>
      <arg type="s" name="bootloader_id" direction="in"/>
      <arg type="b" name="removable" direction="in"/>
      <arg type="s" name="disk" direction="in"/>
      <arg type="s" name="boot_directory" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_GRUB_MKCONFIG = shutil.which("grub-mkconfig") or "/usr/sbin/grub-mkconfig"
_GRUB_INSTALL = shutil.which("grub-install") or "/usr/sbin/grub-install"

_POLKIT = {
    "RegenerateGrub": BOOTLOADER_POLKIT,
    "InstallGrub": BOOTLOADER_INSTALL_POLKIT,
}
_METHODS = tuple(_POLKIT)


def _run(argv: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip()


class BootloaderService:
    """Implements the ``org.gentoo.gest.Bootloader`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            BOOTLOADER_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method not in _METHODS:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, _POLKIT[method]):
            audit(method, uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized for this bootloader operation")
            return
        try:
            if method == "RegenerateGrub":
                ok, out = _run(commands.grub_mkconfig_argv(grub_mkconfig=_GRUB_MKCONFIG))
                detail = "regenerate grub.cfg"
            else:  # InstallGrub
                firmware, efi_dir, boot_id, removable, disk, boot_dir = params.unpack()
                argv = commands.grub_install_argv(
                    firmware, efi_directory=efi_dir, bootloader_id=boot_id,
                    removable=bool(removable), disk=disk, boot_directory=boot_dir,
                    grub_install=_GRUB_INSTALL)
                ok, out = _run(argv)
                detail = f"grub-install {firmware}"
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        audit(method, uid=uid, result="ok" if ok else "failed", detail=detail)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))
