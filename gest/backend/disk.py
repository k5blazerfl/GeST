"""GeST root D-Bus interface for the disks & mounts module.

Registered on the shared bus name at /org/gentoo/gest/Disk. Mounts/unmounts
fstab entries with `mount`/`umount` and edits /etc/fstab (add/edit/remove
non-critical entries). polkit-gated with org.gentoo.gest.disk.manage; every
action is audit-logged.

Safety: the essential mounts (/, /boot, /efi, swap) are refused here, every
fstab field is re-validated server-side (never trust the client), and each write
is atomic and preceded by a /etc/fstab.gest.bak backup.
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
from gest.core.disk import commands, fstab
from gest.core.disk.fstab import FstabEntry
from gest.ipc.interface import DISK_IFACE, DISK_PATH, DISK_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{DISK_IFACE}">
    <method name="Mount">
      <arg type="s" name="mountpoint" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="Unmount">
      <arg type="s" name="mountpoint" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="WriteFstabEntry">
      <arg type="s" name="spec" direction="in"/>
      <arg type="s" name="mountpoint" direction="in"/>
      <arg type="s" name="fstype" direction="in"/>
      <arg type="s" name="options" direction="in"/>
      <arg type="i" name="dump" direction="in"/>
      <arg type="i" name="passno" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="RemoveFstabEntry">
      <arg type="s" name="mountpoint" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_MOUNT = shutil.which("mount") or "/bin/mount"
_UMOUNT = shutil.which("umount") or "/bin/umount"

FSTAB_PATH = "/etc/fstab"
FSTAB_BACKUP = "/etc/fstab.gest.bak"

_METHODS = ("Mount", "Unmount", "WriteFstabEntry", "RemoveFstabEntry")


def _run(argv: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip()


def _atomic_write(path: str, text: str) -> None:
    directory = os.path.dirname(path)
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


class DiskService:
    """Implements the ``org.gentoo.gest.Disk`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            DISK_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method not in _METHODS:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, DISK_POLKIT):
            audit(method, uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to manage disks and mounts")
            return
        try:
            if method == "Mount":
                (mountpoint,) = params.unpack()
                ok, out = _run(commands.mount_argv(mountpoint, mount=_MOUNT))
                detail = f"mount {mountpoint}"
            elif method == "Unmount":
                (mountpoint,) = params.unpack()
                ok, out = _run(commands.umount_argv(mountpoint, umount=_UMOUNT))
                detail = f"umount {mountpoint}"
            elif method == "WriteFstabEntry":
                spec, mountpoint, fstype, options, dump, passno = params.unpack()
                ok, out = self._write_fstab(spec, mountpoint, fstype, options, dump, passno)
                detail = f"fstab write {mountpoint}"
            else:  # RemoveFstabEntry
                (mountpoint,) = params.unpack()
                ok, out = self._remove_fstab(mountpoint)
                detail = f"fstab remove {mountpoint}"
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        except OSError as exc:
            invocation.return_value(GLib.Variant("(bs)", (False, f"write failed: {exc}")))
            return
        audit(method, uid=uid, result="ok" if ok else "failed", detail=detail)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))

    def _read_fstab(self) -> str:
        try:
            with open(FSTAB_PATH, encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return ""

    def _guard_not_protected(self, mountpoint: str, text: str) -> None:
        """Refuse edits to a currently-protected mount point (raises ValueError)."""
        for existing in fstab.parse_fstab(text):
            if existing.mountpoint == mountpoint and fstab.is_protected(existing):
                raise ValueError("protected mount point")

    def _write_fstab(self, spec, mountpoint, fstype, options, dump, passno):
        entry = FstabEntry(spec, mountpoint, fstype, options, int(dump), int(passno))
        if not fstab.valid_entry(entry):
            raise ValueError("invalid fstab entry")
        if fstab.is_protected(entry):
            raise ValueError("protected mount point")
        text = self._read_fstab()
        self._guard_not_protected(mountpoint, text)
        if os.path.exists(FSTAB_PATH):
            shutil.copy2(FSTAB_PATH, FSTAB_BACKUP)
        _atomic_write(FSTAB_PATH, fstab.upsert_entry(text, entry))
        return True, f"{mountpoint} written to /etc/fstab (backup: {FSTAB_BACKUP})"

    def _remove_fstab(self, mountpoint):
        if not fstab.valid_mountpoint(mountpoint):
            raise ValueError("invalid mount point")
        text = self._read_fstab()
        self._guard_not_protected(mountpoint, text)
        if os.path.exists(FSTAB_PATH):
            shutil.copy2(FSTAB_PATH, FSTAB_BACKUP)
        _atomic_write(FSTAB_PATH, fstab.remove_entry(text, mountpoint))
        return True, f"{mountpoint} removed from /etc/fstab (backup: {FSTAB_BACKUP})"
