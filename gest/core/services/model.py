"""Data type for a system service (frontend-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Service:
    name: str
    status: str = "stopped"  # started / stopped / crashed / inactive / …
    runlevels: list[str] = field(default_factory=list)

    @property
    def enabled(self) -> bool:
        return bool(self.runlevels)

    @property
    def running(self) -> bool:
        return self.status == "started"
