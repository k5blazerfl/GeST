"""Pure, validated argv builders for the disk module.

Two families live here: the existing mount/unmount of fstab entries, and the new
*provisioning* builders (`wipefs`, `sgdisk`, `mkfs.*`, `mkswap`/`swapon`) the
partitioner runs. Every builder validates its inputs and raises ``ValueError`` on
anything unsafe — these argv end up running as root, so a device name, size,
type GUID or label that doesn't match a strict pattern is refused here before it
can reach a shell. The builders are pure (no I/O), so the whole surface is
CI-testable without a disk.
"""

from __future__ import annotations

import re

from gest.core.disk.fstab import valid_mount_target
from gest.core.disk.model import Partition

# A real block-device node: /dev/sda, /dev/nvme0n1p2, /dev/mapper/vg-root.
_DEVICE_RE = re.compile(r"\A/dev/[A-Za-z0-9][A-Za-z0-9/_-]*\Z")
# sgdisk-style size: a number with an optional K/M/G/T suffix, or "rest".
_SIZE_RE = re.compile(r"\A(?:rest|\d+[KMGT]?)\Z")
# gdisk type code: four hex digits (EF00, 8300, …).
_GUID_RE = re.compile(r"\A[0-9A-Fa-f]{4}\Z")
# Partition/filesystem label: conservative, no whitespace or metacharacters.
_LABEL_RE = re.compile(r"\A[A-Za-z0-9_-]{1,36}\Z")

# kind -> (program, force-flags, label-flag). The force flags let mkfs overwrite
# an existing signature non-interactively (the plan already gated the wipe).
_MKFS: dict[str, tuple[str, list[str], str]] = {
    "ext4": ("mkfs.ext4", ["-F"], "-L"),
    "xfs": ("mkfs.xfs", ["-f"], "-L"),
    "btrfs": ("mkfs.btrfs", ["-f"], "-L"),
    "f2fs": ("mkfs.f2fs", ["-f"], "-l"),
    "vfat": ("mkfs.vfat", ["-F", "32"], "-n"),
}

FS_KINDS = frozenset(_MKFS) | {"swap"}


# --- mount / unmount (existing) --------------------------------------------

def mount_argv(mountpoint: str, *, mount: str = "mount") -> list[str]:
    """Mount a filesystem already defined in fstab: `mount <mountpoint>`."""
    if not valid_mount_target(mountpoint):
        raise ValueError(f"invalid mount point: {mountpoint!r}")
    return [mount, mountpoint]


def umount_argv(mountpoint: str, *, umount: str = "umount") -> list[str]:
    """Unmount a mounted filesystem: `umount <mountpoint>`."""
    if not valid_mount_target(mountpoint):
        raise ValueError(f"invalid mount point: {mountpoint!r}")
    return [umount, mountpoint]


# --- validation helpers -----------------------------------------------------

def valid_device(device: str) -> bool:
    """A path we're willing to hand to a destructive tool as its target."""
    return bool(_DEVICE_RE.match(device)) and ".." not in device and len(device) <= 255


def _require_device(device: str) -> None:
    if not valid_device(device):
        raise ValueError(f"invalid block device: {device!r}")


def _require_size(size: str) -> None:
    if not _SIZE_RE.match(size):
        raise ValueError(f"invalid partition size: {size!r}")


def _require_guid(guid: str) -> None:
    if not _GUID_RE.match(guid):
        raise ValueError(f"invalid partition type code: {guid!r}")


def _require_label(label: str) -> None:
    if not _LABEL_RE.match(label):
        raise ValueError(f"invalid label: {label!r}")


# --- provisioning builders --------------------------------------------------

def wipefs_argv(device: str, *, wipefs: str = "wipefs", dry: bool = False) -> list[str]:
    """Erase filesystem/partition-table signatures: `wipefs -a <device>`.

    ``dry=True`` builds the no-op `wipefs -n` used for the preview.
    """
    _require_device(device)
    return [wipefs, "-n" if dry else "-a", device]


def sgdisk_zap_argv(device: str, *, sgdisk: str = "sgdisk") -> list[str]:
    """Destroy any existing GPT/MBR: `sgdisk --zap-all <device>`."""
    _require_device(device)
    return [sgdisk, "--zap-all", device]


def sgdisk_partition_argv(
    device: str, partitions: list[Partition], *, sgdisk: str = "sgdisk"
) -> list[str]:
    """Create every partition in one `sgdisk` call.

    Each partition becomes ``-n N:0:+SIZE -t N:GUID [-c N:LABEL]``; ``size ==
    "rest"`` maps to sgdisk's ``0`` end sentinel (fill remaining space).
    """
    _require_device(device)
    if not partitions:
        raise ValueError("no partitions to create")
    argv = [sgdisk]
    for part in partitions:
        _require_size(part.size)
        _require_guid(part.type_guid)
        end = "0" if part.size == "rest" else f"+{part.size}"
        argv += ["-n", f"{part.number}:0:{end}", "-t", f"{part.number}:{part.type_guid}"]
        if part.label:
            _require_label(part.label)
            argv += ["-c", f"{part.number}:{part.label}"]
    argv.append(device)
    return argv


def partprobe_argv(device: str, *, partprobe: str = "partprobe") -> list[str]:
    """Ask the kernel to re-read the partition table: `partprobe <device>`."""
    _require_device(device)
    return [partprobe, device]


def udevadm_settle_argv(*, udevadm: str = "udevadm") -> list[str]:
    """Wait for udev to finish creating the new partition nodes."""
    return [udevadm, "settle"]


def mkfs_argv(device: str, kind: str, label: str | None = None) -> list[str]:
    """Build the `mkfs.<kind>` argv for ``device`` (optionally labelled)."""
    _require_device(device)
    if kind not in _MKFS:
        raise ValueError(f"unsupported filesystem: {kind!r}")
    program, flags, label_flag = _MKFS[kind]
    argv = [program, *flags]
    if label:
        _require_label(label)
        argv += [label_flag, label]
    argv.append(device)
    return argv


def mkswap_argv(device: str, label: str | None = None, *, mkswap: str = "mkswap") -> list[str]:
    """Initialise swap on ``device``: `mkswap [-L label] <device>`."""
    _require_device(device)
    argv = [mkswap]
    if label:
        _require_label(label)
        argv += ["-L", label]
    argv.append(device)
    return argv


def swapon_argv(device: str, *, swapon: str = "swapon") -> list[str]:
    """Enable swap on ``device``: `swapon <device>`."""
    _require_device(device)
    return [swapon, device]


def swapoff_argv(device: str, *, swapoff: str = "swapoff") -> list[str]:
    """Disable swap on ``device``: `swapoff <device>`."""
    _require_device(device)
    return [swapoff, device]
