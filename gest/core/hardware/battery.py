"""Battery state via /sys/class/power_supply (unprivileged; injectable root)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Battery:
    present: bool = False
    percent: int = 0
    status: str = "Unknown"  # Charging / Discharging / Full / Not charging / Unknown

    @property
    def charging(self) -> bool:
        return self.status in ("Charging", "Full")


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def read_battery(power_supply_root: str = "/sys/class/power_supply") -> Battery:
    """The first power-supply of type ``Battery``; ``present=False`` if none."""
    try:
        names = sorted(os.listdir(power_supply_root))
    except OSError:
        return Battery()
    for name in names:
        base = os.path.join(power_supply_root, name)
        if _read(os.path.join(base, "type")) != "Battery":
            continue
        try:
            percent = int(_read(os.path.join(base, "capacity")))
        except ValueError:
            percent = 0
        percent = max(0, min(100, percent))
        status = _read(os.path.join(base, "status")) or "Unknown"
        return Battery(present=True, percent=percent, status=status)
    return Battery()
