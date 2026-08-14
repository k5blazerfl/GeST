"""The module registry — Qt-free, so it is unit-testable without a display.

A module is a :class:`ModuleDescriptor` plus a factory that builds its widget.
The factory is opaque here (never called), so registering/grouping needs no Qt
and a module's ``core`` reader runs only when the module is first opened.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModuleDescriptor:
    id: str
    title: str
    category: str
    icon: str = ""


@dataclass
class ModuleEntry:
    descriptor: ModuleDescriptor
    factory: Callable[[], Any]  # -> QWidget (kept as Any to avoid a Qt import)


class Registry:
    def __init__(self) -> None:
        self._entries: dict[str, ModuleEntry] = {}

    def register(self, descriptor: ModuleDescriptor, factory: Callable[[], Any]) -> None:
        """Add a module; a later registration for the same id replaces it."""
        self._entries[descriptor.id] = ModuleEntry(descriptor, factory)

    def entries(self) -> list[ModuleEntry]:
        """All modules, sorted by (category, title)."""
        return sorted(
            self._entries.values(),
            key=lambda e: (e.descriptor.category.lower(), e.descriptor.title.lower()),
        )

    def by_category(self) -> dict[str, list[ModuleEntry]]:
        """Modules grouped by category (categories in first-seen sorted order,
        modules title-sorted within each)."""
        grouped: dict[str, list[ModuleEntry]] = {}
        for entry in self.entries():
            grouped.setdefault(entry.descriptor.category, []).append(entry)
        return grouped
