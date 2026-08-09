"""Pure, validated argv builders for mount/unmount of fstab entries."""

from __future__ import annotations

from gest.core.disk.fstab import valid_mount_target


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
