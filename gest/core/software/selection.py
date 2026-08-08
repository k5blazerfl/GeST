"""Pending package changes for the transactional Software Management flow.

The YaST model: mark packages, then commit them together with Accept. This is
the frontend-agnostic store of those marks — pure data, no Portage/toolkit
imports, so it is unit-testable on CI. Currently it tracks install marks; the
mark set is a dict so remove/update can slot in later without a rewrite.
"""

from __future__ import annotations

INSTALL = "install"


class Selection:
    """A set of pending package marks keyed by ``cp`` (category/package)."""

    def __init__(self) -> None:
        self._marks: dict[str, str] = {}

    def mark_install(self, cp: str) -> None:
        self._marks[cp] = INSTALL

    def unmark(self, cp: str) -> None:
        self._marks.pop(cp, None)

    def toggle_install(self, cp: str) -> None:
        if self._marks.get(cp) == INSTALL:
            self.unmark(cp)
        else:
            self.mark_install(cp)

    def mark_of(self, cp: str) -> str | None:
        return self._marks.get(cp)

    def is_marked(self, cp: str) -> bool:
        return cp in self._marks

    def clear(self) -> None:
        self._marks.clear()

    @property
    def is_empty(self) -> bool:
        return not self._marks

    def install_atoms(self) -> list[str]:
        return sorted(cp for cp, mark in self._marks.items() if mark == INSTALL)

    def summary(self) -> str:
        n = len(self.install_atoms())
        return f"{n} to install" if n else "no changes"

    def __len__(self) -> int:
        return len(self._marks)
