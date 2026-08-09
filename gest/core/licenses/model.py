"""Data types for the licenses module."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class LicenseEntry:
    """One per-package acceptance — an atom and the licenses accepted for it."""

    atom: str
    licenses: list[str] = field(default_factory=list)
    managed: bool = False  # True if it lives in GeST's package.license/gest file
