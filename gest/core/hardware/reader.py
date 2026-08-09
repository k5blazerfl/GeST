"""Read a read-only hardware inventory as the invoking user (no mutations).

Sources, all unprivileged:
  lscpu                       → CPU model, topology, caches
  /proc/meminfo               → RAM / swap totals
  lsblk                       → block devices & mount points
  lspci / lsusb               → PCI / USB device list
  /sys/class/dmi/id/*         → world-readable firmware/board identity

Each `parse_*`/`dmi_info` function is pure over its input text so it can be
tested in CI; `inventory()` wires them to the live host. A missing tool or
unreadable file yields an empty section rather than an error.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable

from gest.core.hardware.model import Section

Runner = Callable[[list[str]], str]

DMI_DIR = "/sys/class/dmi/id"
MEMINFO = "/proc/meminfo"

# Curated DMI attributes (filename → label). These specific files are
# world-readable; the serial/UUID ones (which need root) are deliberately left
# out so the whole module stays unprivileged.
_DMI_FIELDS: list[tuple[str, str]] = [
    ("sys_vendor", "Vendor"),
    ("product_name", "Product"),
    ("product_version", "Version"),
    ("board_vendor", "Board vendor"),
    ("board_name", "Board"),
    ("bios_vendor", "BIOS vendor"),
    ("bios_version", "BIOS version"),
    ("bios_date", "BIOS date"),
]

# /proc/meminfo keys to surface (label), in display order.
_MEM_FIELDS: list[tuple[str, str]] = [
    ("MemTotal", "Total"),
    ("MemAvailable", "Available"),
    ("MemFree", "Free"),
    ("SwapTotal", "Swap total"),
    ("SwapFree", "Swap free"),
]


def _default_runner(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True).stdout
    except OSError:
        return ""


def _read_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _nonempty_lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.splitlines() if line.strip()]


def _human_kib(kib: int) -> str:
    """Render a size given in KiB (as /proc/meminfo reports) human-readably."""
    value = float(kib)
    for unit in ("KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"


def parse_lscpu(text: str) -> list[str]:
    """Reformat `lscpu` key/value output into aligned lines.

    The very long ``Flags:`` line is dropped — it's noise in a summary view.
    """
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("Flags:"):
            continue
        key, sep, value = raw.partition(":")
        if sep:
            lines.append(f"{key.strip():<22}: {value.strip()}")
        else:
            lines.append(stripped)
    return lines


def parse_meminfo(text: str) -> list[str]:
    """Pull the totals we care about out of /proc/meminfo (values are in kB)."""
    values: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            values[key.strip()] = int(parts[0])
    return [
        f"{label:<14}: {_human_kib(values[key])}"
        for key, label in _MEM_FIELDS
        if key in values
    ]


def dmi_info(dmi_dir: str = DMI_DIR) -> list[str]:
    """Read the curated, world-readable DMI attributes as aligned lines."""
    lines: list[str] = []
    for fname, label in _DMI_FIELDS:
        value = _read_file(os.path.join(dmi_dir, fname)).strip()
        if value:
            lines.append(f"{label:<14}: {value}")
    return lines


def inventory(
    runner: Runner | None = None,
    *,
    dmi_dir: str = DMI_DIR,
    meminfo_path: str = MEMINFO,
) -> list[Section]:
    """Gather every category from the live host into ordered `Section`s.

    Sections whose source tool is missing come back with an empty ``lines`` list
    (the frontend renders a placeholder); the ``System`` section is omitted
    entirely when no DMI data is readable.
    """
    run = runner or _default_runner
    sections: list[Section] = []

    system = dmi_info(dmi_dir)
    if system:
        sections.append(Section("system", "System", system))

    sections.append(Section("cpu", "CPU", parse_lscpu(run(["lscpu"]))))
    sections.append(Section("memory", "Memory", parse_meminfo(_read_file(meminfo_path))))
    sections.append(Section(
        "storage", "Storage",
        _nonempty_lines(run(["lsblk", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS"])),
    ))
    sections.append(Section("pci", "PCI devices", _nonempty_lines(run(["lspci"]))))
    sections.append(Section("usb", "USB devices", _nonempty_lines(run(["lsusb"]))))
    return sections
