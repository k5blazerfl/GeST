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
    from_binary: bool = False   # installed from a binary package (VDB has BUILD_ID)
    world_member: bool = False
    available_version: str = ""  # newer version available in this slot, if any
    use_flags: list[UseFlag] = field(default_factory=list)

    @property
    def upgradable(self) -> bool:
        """Installed, with a newer version available in the same slot."""
        return self.installed and bool(self.available_version)

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


@dataclass(slots=True)
class PackageDetail:
    """Richer per-package info for the detail pane (available vs installed)."""

    cp: str
    available_version: str = ""
    installed_version: str = ""
    slot: str = "0"
    license: str = ""
    homepage: str = ""
    description: str = ""
    keywords: str = ""
    installed_size: int = 0  # bytes, installed version
    download_size: int = 0   # bytes, distfiles for the best available version
    from_binary: bool = False  # installed version came from a binary package
    required_by: list[str] = field(default_factory=list)  # installed dependents

    @property
    def name(self) -> str:
        return self.cp.split("/", 1)[-1]

    @property
    def installed(self) -> bool:
        return bool(self.installed_version)
