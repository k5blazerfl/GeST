"""Read block devices (`lsblk`) and /etc/fstab — unprivileged, no mutations.

`lsblk -J` gives a structured device tree; /etc/fstab is world-readable. Both
parsers are pure over their input so they're CI-testable; the module functions
wire them to the live host.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

from gest.core.disk import fstab
from gest.core.disk.fstab import FstabEntry
from gest.core.disk.model import BlockDevice

Runner = Callable[[list[str]], str]

FSTAB = "/etc/fstab"


def _mountpoint(entry: dict) -> str:
    """lsblk reports either `mountpoint` (scalar) or `mountpoints` (list)."""
    if entry.get("mountpoint"):
        return entry["mountpoint"]
    for mp in entry.get("mountpoints", []) or []:
        if mp:
            return mp
    return ""


def _device(entry: dict) -> BlockDevice:
    return BlockDevice(
        name=entry.get("name", "?"),
        size=entry.get("size", "") or "",
        type=entry.get("type", "") or "",
        fstype=entry.get("fstype", "") or "",
        mountpoint=_mountpoint(entry),
        children=[_device(child) for child in entry.get("children", []) or []],
    )


def parse_lsblk_json(text: str) -> list[BlockDevice]:
    """Parse the JSON from `lsblk -J` into a BlockDevice tree."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []
    return [_device(entry) for entry in data.get("blockdevices", []) if isinstance(entry, dict)]


def _default_runner(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True).stdout
    except OSError:
        return ""


def list_block_devices(runner: Runner | None = None) -> list[BlockDevice]:
    run = runner or _default_runner
    return parse_lsblk_json(run(["lsblk", "-J", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS"]))


def read_fstab(path: str = FSTAB) -> list[FstabEntry]:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = ""
    return fstab.parse_fstab(text)
