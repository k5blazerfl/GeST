"""Data model for the disks & mounts module.

`BlockDevice` is the read side (the `lsblk` tree). `Partition` / `Filesystem` /
`DiskPlan` are the *provisioning* side: a declarative description of what a disk
should be turned into, reviewed as a whole and then applied by an ordered
pipeline (see `provision.py`). Keeping the plan a plain value type means the UI
can render a current-vs-planned diff and the safety validator can inspect it
without anything having touched a disk yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class BlockDevice:
    """One node of the `lsblk` tree (a disk, partition, LVM/LUKS mapping, …)."""

    name: str
    size: str = ""
    type: str = ""
    fstype: str = ""
    mountpoint: str = ""
    children: list[BlockDevice] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class Partition:
    """One partition to create on the target disk.

    ``size`` is an sgdisk-style size (``"512M"``, ``"8G"``) or ``"rest"`` for the
    remaining space. ``type_guid`` is a gdisk type code (``EF00`` EFI system,
    ``8200`` swap, ``8300`` Linux filesystem, ``8E00`` LVM, ``FD00`` RAID).
    """

    number: int
    size: str
    type_guid: str
    label: str | None = None


@dataclass(slots=True, frozen=True)
class Filesystem:
    """A filesystem (or swap) to make on an already-created partition.

    ``device`` is the partition node it lands on (e.g. ``/dev/sda2``); ``kind``
    is one of the filesystems `commands` knows, or ``"swap"``.
    """

    device: str
    kind: str
    label: str | None = None


@dataclass(slots=True, frozen=True)
class DiskPlan:
    """A whole-disk provisioning plan: wipe? → partitions → filesystems."""

    disk: str
    wipe: bool
    partitions: list[Partition] = field(default_factory=list)
    filesystems: list[Filesystem] = field(default_factory=list)
