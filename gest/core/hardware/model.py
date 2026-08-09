"""Data model for the hardware inventory module."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Section:
    """One category of the inventory (e.g. CPU) as pre-formatted detail lines."""

    key: str
    title: str
    lines: list[str] = field(default_factory=list)
