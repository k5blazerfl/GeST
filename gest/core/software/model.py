"""Plain data types for the software module.

These are frontend-agnostic: the TUI, a future Qt/KDE frontend, and the tests
all consume the same dataclasses. Nothing here imports Portage or a toolkit.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class UseFlag:
    """A single USE flag on a package."""

    name: str
    enabled: bool
    description: str = ""

    def __str__(self) -> str:  # e.g. "+X" / "-wayland"
        return f"{'+' if self.enabled else '-'}{self.name}"


@dataclass(slots=True)
class Package:
    """A concrete package version, installed or available."""

    cp: str  # category/package, e.g. "www-client/firefox"
    version: str  # e.g. "128.4.0"
    slot: str = "0"
    description: str = ""
    repository: str = ""
    homepage: str = ""
    installed: bool = False
    world_member: bool = False
    use_flags: list[UseFlag] = field(default_factory=list)

    @property
    def cpv(self) -> str:
        return f"{self.cp}-{self.version}" if self.version else self.cp

    @property
    def name(self) -> str:
        return self.cp.split("/", 1)[-1]

    @property
    def category(self) -> str:
        return self.cp.split("/", 1)[0] if "/" in self.cp else ""


@dataclass(slots=True)
class SearchResult:
    """A lightweight hit for search listings (no per-flag detail)."""

    cp: str
    best_version: str
    description: str = ""
    installed_version: str | None = None

    @property
    def installed(self) -> bool:
        return self.installed_version is not None

    @property
    def name(self) -> str:
        return self.cp.split("/", 1)[-1]
