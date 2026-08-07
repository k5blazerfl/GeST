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


@dataclass(slots=True)
class ServiceDetail:
    """Introspected detail for one service (read-only, from `rc-service`)."""

    name: str
    description: str = ""
    needs: list[str] = field(default_factory=list)       # rc-service X ineed
    uses: list[str] = field(default_factory=list)        # rc-service X iuse
    wants: list[str] = field(default_factory=list)       # rc-service X iwant
    needed_by: list[str] = field(default_factory=list)   # rc-service X needsme
    status: str = "stopped"
    runlevels: list[str] = field(default_factory=list)

    @property
    def running(self) -> bool:
        return self.status == "started"
