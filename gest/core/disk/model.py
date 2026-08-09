"""Data model for the disks & mounts module."""

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
