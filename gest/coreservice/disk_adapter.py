"""Pure adapter for the Disks & mounts core module."""

from __future__ import annotations

from typing import Any

from gest.core.disk import reader


def device_to_dict(b: Any) -> dict[str, Any]:
    return {
        "name": b.name,
        "size": b.size,
        "type": b.type,
        "fstype": b.fstype,
        "mountpoint": b.mountpoint,
    }


def list_devices() -> list[dict[str, Any]]:
    return [device_to_dict(b) for b in reader.list_block_devices()]
