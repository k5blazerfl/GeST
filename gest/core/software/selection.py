"""Pending package changes for the transactional Software Management flow.

The YaST model: mark packages, then commit them together with Accept. This is
the frontend-agnostic store of those marks — pure data, no Portage/toolkit
imports, so it is unit-testable on CI. Currently it tracks install marks; the
mark set is a dict so remove/update can slot in later without a rewrite.
"""

from __future__ import annotations

INSTALL = "install"          # build/update from source (plain emerge)
BINPKG = "binpkg"            # install binary only  (emerge --getbinpkg --usepkgonly)
BINPREF = "binpref"          # prefer binary, else source (emerge --getbinpkg)
REMOVE = "remove"


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

    def mark_remove(self, cp: str) -> None:
        self._marks[cp] = REMOVE

    def toggle_remove(self, cp: str) -> None:
        if self._marks.get(cp) == REMOVE:
            self.unmark(cp)
        else:
            self.mark_remove(cp)

    def toggle(self, cp: str, mark: str) -> None:
        """Toggle an arbitrary mark (install/binpkg/binpref/remove)."""
        if self._marks.get(cp) == mark:
            self.unmark(cp)
        else:
            self._marks[cp] = mark

    def set(self, cp: str, mark: str | None) -> None:
        """Force ``cp`` to ``mark`` (or clear it when ``mark`` is None)."""
        if mark is None:
            self.unmark(cp)
        else:
            self._marks[cp] = mark

    def mark_of(self, cp: str) -> str | None:
        return self._marks.get(cp)

    def is_marked(self, cp: str) -> bool:
        return cp in self._marks

    def clear(self) -> None:
        self._marks.clear()

    @property
    def is_empty(self) -> bool:
        return not self._marks

    def _atoms(self, mark: str) -> list[str]:
        return sorted(cp for cp, m in self._marks.items() if m == mark)

    def install_atoms(self) -> list[str]:
        return self._atoms(INSTALL)

    def binpkg_atoms(self) -> list[str]:
        return self._atoms(BINPKG)

    def binpref_atoms(self) -> list[str]:
        return self._atoms(BINPREF)

    def remove_atoms(self) -> list[str]:
        return self._atoms(REMOVE)

    def summary(self) -> str:
        parts = []
        for n, label in (
            (len(self.install_atoms()), "to install"),
            (len(self.binpkg_atoms()), "binary"),
            (len(self.binpref_atoms()), "prefer-binary"),
            (len(self.remove_atoms()), "to remove"),
        ):
            if n:
                parts.append(f"{n} {label}")
        return " · ".join(parts) if parts else "no changes"

    def __len__(self) -> int:
        return len(self._marks)
