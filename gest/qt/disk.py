"""Disk module logic: a pure block-device label (read-only)."""

from __future__ import annotations

from gest.core.disk.model import BlockDevice


def device_label(dev: BlockDevice) -> str:
    parts = [dev.name]
    if dev.size:
        parts.append(dev.size)
    if dev.fstype:
        parts.append(dev.fstype)
    if dev.mountpoint:
        parts.append(f"→ {dev.mountpoint}")
    return "  ".join(parts)
