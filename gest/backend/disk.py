"""GeST root D-Bus interface for the disks & mounts module.

Registered on the shared bus name at /org/gentoo/gest/Disk. Two families of
methods:

* **mounts & fstab** — mount/unmount fstab entries and add/edit/remove
  non-critical /etc/fstab lines (gated by ``disk.manage``).
* **provisioning** — partition a disk, make filesystems, make/enable swap (gated
  by the distinct ``disk.partition`` / ``disk.mkfs`` / ``disk.swap`` actions so a
  policy can authorize each destructive class independently).

Every action is polkit-gated and audit-logged. Safety: the essential mounts
(/, /boot, /efi, swap) are refused for fstab edits; every provisioning target is
re-validated server-side (`provision.guard_provision_target` — never trust the
client) so a mounted device, or the device backing the running system, can never
be repartitioned or reformatted, and each target must be a real block device.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import stat
import subprocess
import tempfile

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.audit import audit
from gest.backend.polkit import caller_uid, check_authorization
from gest.core.disk import commands, fstab, provision
from gest.core.disk.fstab import FstabEntry
from gest.core.disk.model import Partition
from gest.ipc.interface import (
    DISK_IFACE,
    DISK_MKFS_POLKIT,
    DISK_PARTITION_POLKIT,
    DISK_PATH,
    DISK_POLKIT,
    DISK_SWAP_POLKIT,
)

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
    <method name="PartitionDisk">
      <arg type="s" name="disk" direction="in"/>
      <arg type="b" name="wipe" direction="in"/>
      <arg type="a(isss)" name="partitions" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="MakeFilesystem">
      <arg type="s" name="device" direction="in"/>
      <arg type="s" name="kind" direction="in"/>
      <arg type="s" name="label" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="MakeSwap">
      <arg type="s" name="device" direction="in"/>
      <arg type="s" name="label" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="SwapOn">
      <arg type="s" name="device" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="SwapOff">
      <arg type="s" name="device" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_MOUNT = shutil.which("mount") or "/bin/mount"
_UMOUNT = shutil.which("umount") or "/bin/umount"
_WIPEFS = shutil.which("wipefs") or "/sbin/wipefs"
_SGDISK = shutil.which("sgdisk") or "/usr/sbin/sgdisk"
_PARTPROBE = shutil.which("partprobe") or "/usr/sbin/partprobe"
_UDEVADM = shutil.which("udevadm") or "/sbin/udevadm"
_MKSWAP = shutil.which("mkswap") or "/sbin/mkswap"
_SWAPON = shutil.which("swapon") or "/sbin/swapon"
_SWAPOFF = shutil.which("swapoff") or "/sbin/swapoff"

FSTAB_PATH = "/etc/fstab"
FSTAB_BACKUP = "/etc/fstab.gest.bak"
PROC_MOUNTS = "/proc/mounts"

# Each method's polkit action. Provisioning is split by destructive class.
_POLKIT = {
    "Mount": DISK_POLKIT,
    "Unmount": DISK_POLKIT,
    "WriteFstabEntry": DISK_POLKIT,
    "RemoveFstabEntry": DISK_POLKIT,
    "PartitionDisk": DISK_PARTITION_POLKIT,
    "MakeFilesystem": DISK_MKFS_POLKIT,
    "MakeSwap": DISK_SWAP_POLKIT,
    "SwapOn": DISK_SWAP_POLKIT,
    "SwapOff": DISK_SWAP_POLKIT,
}
_METHODS = tuple(_POLKIT)


def _run(argv: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip()


def _run_sequence(steps: list[list[str]], success_msg: str) -> tuple[bool, str]:
    """Run argv steps in order, stopping at the first failure."""
    collected: list[str] = []
    for argv in steps:
        ok, out = _run(argv)
        if out:
            collected.append(out)
        if not ok:
            return False, "\n".join(collected)
    return True, "\n".join(collected) if collected else success_msg


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
        if not check_authorization(self._conn, sender, _POLKIT[method]):
            audit(method, uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized for this disk operation")
            return
        try:
            ok, out, detail = self._dispatch(method, params)
        except provision.DiskSafetyError as exc:
            audit(method, uid=uid, result="refused", detail=str(exc))
            invocation.return_value(GLib.Variant("(bs)", (False, f"refused: {exc}")))
            return
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        except OSError as exc:
            invocation.return_value(GLib.Variant("(bs)", (False, f"failed: {exc}")))
            return
        audit(method, uid=uid, result="ok" if ok else "failed", detail=detail)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))

    def _dispatch(self, method: str, params) -> tuple[bool, str, str]:
        """Run ``method``; return ``(ok, output, audit_detail)``."""
        if method == "Mount":
            (mountpoint,) = params.unpack()
            ok, out = _run(commands.mount_argv(mountpoint, mount=_MOUNT))
            return ok, out, f"mount {mountpoint}"
        if method == "Unmount":
            (mountpoint,) = params.unpack()
            ok, out = _run(commands.umount_argv(mountpoint, umount=_UMOUNT))
            return ok, out, f"umount {mountpoint}"
        if method == "WriteFstabEntry":
            spec, mountpoint, fstype, options, dump, passno = params.unpack()
            ok, out = self._write_fstab(spec, mountpoint, fstype, options, dump, passno)
            return ok, out, f"fstab write {mountpoint}"
        if method == "RemoveFstabEntry":
            (mountpoint,) = params.unpack()
            ok, out = self._remove_fstab(mountpoint)
            return ok, out, f"fstab remove {mountpoint}"
        if method == "PartitionDisk":
            disk, wipe, partitions = params.unpack()
            ok, out = self._partition(disk, wipe, partitions)
            return ok, out, f"partition {disk}"
        if method == "MakeFilesystem":
            device, kind, label = params.unpack()
            ok, out = self._make_filesystem(device, kind, label)
            return ok, out, f"mkfs {kind} {device}"
        if method == "MakeSwap":
            device, label = params.unpack()
            ok, out = self._make_swap(device, label)
            return ok, out, f"mkswap {device}"
        if method == "SwapOn":
            (device,) = params.unpack()
            ok, out = self._swapon(device)
            return ok, out, f"swapon {device}"
        # SwapOff
        (device,) = params.unpack()
        ok, out = self._swapoff(device)
        return ok, out, f"swapoff {device}"

    # --- provisioning -------------------------------------------------------

    def _read_mounts(self) -> str:
        try:
            with open(PROC_MOUNTS, encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return ""

    def _require_block_device(self, device: str) -> None:
        """Server-side re-check: a real, present block device (raises ValueError)."""
        if not commands.valid_device(device):
            raise ValueError(f"invalid block device: {device!r}")
        try:
            mode = os.stat(device).st_mode
        except OSError as exc:
            raise ValueError(f"{device}: {exc.strerror or 'cannot stat'}") from exc
        if not stat.S_ISBLK(mode):
            raise ValueError(f"{device} is not a block device")

    def _partition(self, disk, wipe, partitions) -> tuple[bool, str]:
        provision.guard_provision_target(disk, self._read_mounts(), whole_disk=True)
        self._require_block_device(disk)
        parts = [Partition(int(n), size, guid, label or None)
                 for (n, size, guid, label) in partitions]
        steps: list[list[str]] = []
        if wipe:
            steps.append(commands.wipefs_argv(disk, wipefs=_WIPEFS))
            steps.append(commands.sgdisk_zap_argv(disk, sgdisk=_SGDISK))
        steps.append(commands.sgdisk_partition_argv(disk, parts, sgdisk=_SGDISK))
        steps.append(commands.partprobe_argv(disk, partprobe=_PARTPROBE))
        steps.append(commands.udevadm_settle_argv(udevadm=_UDEVADM))
        return _run_sequence(steps, f"partitioned {disk}")

    def _make_filesystem(self, device, kind, label) -> tuple[bool, str]:
        provision.guard_provision_target(device, self._read_mounts(), whole_disk=False)
        self._require_block_device(device)
        ok, out = _run(commands.mkfs_argv(device, kind, label or None))
        return ok, out or f"made {kind} on {device}"

    def _make_swap(self, device, label) -> tuple[bool, str]:
        provision.guard_provision_target(device, self._read_mounts(), whole_disk=False)
        self._require_block_device(device)
        ok, out = _run(commands.mkswap_argv(device, label or None, mkswap=_MKSWAP))
        return ok, out or f"swap ready on {device}"

    def _swapon(self, device) -> tuple[bool, str]:
        self._require_block_device(device)
        ok, out = _run(commands.swapon_argv(device, swapon=_SWAPON))
        return ok, out or f"swap enabled on {device}"

    def _swapoff(self, device) -> tuple[bool, str]:
        self._require_block_device(device)
        ok, out = _run(commands.swapoff_argv(device, swapoff=_SWAPOFF))
        return ok, out or f"swap disabled on {device}"

    # --- mounts & fstab -----------------------------------------------------

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
