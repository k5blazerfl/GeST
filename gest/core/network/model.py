"""Data type for a network interface."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Interface:
    name: str
    state: str = "UNKNOWN"       # UP / DOWN / UNKNOWN (operstate)
    mac: str = ""
    addresses: list[str] = field(default_factory=list)  # "192.168.1.5/24"

    @property
    def up(self) -> bool:
        return self.state.upper() == "UP"

    @property
    def loopback(self) -> bool:
        return self.name == "lo"
