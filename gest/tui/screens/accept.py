"""Software Management Accept (urwid): organized install + remove progress.

Replaces the raw streaming ApplyScreen dump for the Accept flow. Accept can both
install/update packages and remove others (a depclean pass), so this seeds a row
per marked package and advances each from emerge's markers — installs via
``>>> Emerging/Installing (N of M) …`` (pending → building → installed), removals
via ``>>> Unmerging (N of M) …`` (pending → removing → removed) — with a progress
bar and a combined result. The plans run sequentially (installs, then removals);
the full raw log is kept on demand (l / View log).
"""

from __future__ import annotations

from gest.core.software.cleanup import parse_unmerge
from gest.core.software.update import parse_merge_progress, split_cpv
from gest.tui.runtime import App
from gest.tui.screens.apply import install_binary_plan, install_plan, remove_plan
from gest.tui.screens.runscreen import RunScreen, clip

_STATUS_W = 2
_CAT_W = 16
_PKG_W = 26

# active = building (install) or removing (remove); done = installed / removed.
_GLYPH = {"pending": "·", "active": "▸", "done": "✓", "failed": "✗"}
_ATTR = {"pending": "dim", "active": None, "done": "dim", "failed": "error"}


def _fmt(glyph: str, cat: str, pkg: str, op: str) -> str:
    return (f"{glyph:<{_STATUS_W}}{clip(cat, _CAT_W):<{_CAT_W}}"
            f"{clip(pkg, _PKG_W):<{_PKG_W}}{op}")


class _Item:
    __slots__ = ("category", "cp", "detail", "kind", "package", "status")

    def __init__(self, cp: str, kind: str):
        self.cp, self.kind = cp, kind          # kind: "install" | "remove"
        self.category, _, self.package = cp.partition("/")
        if not self.package:
            self.package = cp
        self.detail = ""                       # version, filled from the markers
        self.status = "pending"

    def op_text(self) -> str:
        label = "install" if self.kind == "install" else "remove"
        return f"{label} {self.detail}" if self.detail else label


class AcceptRunScreen(RunScreen):
    """Organized install + remove progress (Emerging/Installing + Unmerging)."""

    HEADER = _fmt("", "Category", "Package", "Operation")
    TABLE_TITLE = "Applying changes"
    SCREEN_TITLE = "Software Management"
    RUN_PHASE = "Applying changes …"
    EMPTY_TEXT = " (nothing to apply)"
    STATUS_GLYPH = _GLYPH
    STATUS_ATTR = _ATTR
    ACTIVE_STATUSES = ("active",)
    DONE_STATUS = "done"

    def __init__(self, app: App, *, installs=(), binpkgs=(), binprefs=(),
                 removes=(), verb: str = "Accept", on_done=None):
        self._installs = list(installs)
        self._binpkgs = list(binpkgs)
        self._binprefs = list(binprefs)
        self._removes = list(removes)
        self._plans = []
        if self._installs:
            self._plans.append(install_plan(self._installs))
        if self._binpkgs:
            self._plans.append(install_binary_plan(self._binpkgs, only=True))
        if self._binprefs:
            self._plans.append(install_binary_plan(self._binprefs, only=False))
        if self._removes:
            self._plans.append(remove_plan(self._removes))
        super().__init__(app, on_done=on_done)

    def _build_items(self):
        items = [_Item(cp, "install")
                 for cp in (*self._installs, *self._binpkgs, *self._binprefs)]
        items += [_Item(cp, "remove") for cp in self._removes]
        self._install = {it.cp: it for it in items if it.kind == "install"}
        self._remove = {it.cp: it for it in items if it.kind == "remove"}
        return items

    def _row_text(self, it) -> str:
        return _fmt(self._glyph(it.status), it.category, it.package, it.op_text())

    def _operations(self):
        return [plan.run for plan in self._plans]

    def _consume(self, line: str) -> None:
        p = parse_merge_progress(line)
        if p is not None:
            cp, ver = split_cpv(p.atom)
            line = self._install.get(cp) or self._add(cp, "install")
            line.detail = ver
            line.status = "active" if p.phase == "Emerging" else "done"
            self._set_phase(f"{p.phase} {p.n} of {p.total} — {p.atom}")
            self._advance()
            return
        u = parse_unmerge(line)
        if u is not None:
            cp, ver = split_cpv(u.atom)
            for it in self._items:             # unmerge has one marker per package
                if it.kind == "remove" and it.status == "active":
                    it.status = "done"
            line = self._remove.get(cp) or self._add(cp, "remove")
            line.detail = ver
            line.status = "active"
            self._set_phase(f"Removing {u.atom}")
            self._advance()

    def _add(self, cp: str, kind: str) -> _Item:
        item = self._append(_Item(cp, kind))
        (self._install if kind == "install" else self._remove)[cp] = item
        return item

    def _summary(self, code: int):
        installed = sum(1 for it in self._items
                        if it.kind == "install" and it.status == "done")
        removed = sum(1 for it in self._items
                      if it.kind == "remove" and it.status == "done")
        if code == 0:
            parts = []
            if installed:
                parts.append(f"installed {installed}")
            if removed:
                parts.append(f"removed {removed}")
            return "Completed", True, (
                f"Done — {', '.join(parts) or 'no changes'} package(s).")
        return "Failed", False, (
            f"emerge exited {code}. The changes may be incomplete; see the log.")

    def _help_text(self) -> str:
        return (
            "Applying the marked changes with emerge (installs first, then a\n"
            "depclean removal pass).\n\n"
            "Each row shows its status:  · pending   ▸ in progress   ✓ done"
            "   ✗ failed\n"
            "Packages pulled in as dependencies appear as they are built.\n"
            "The full raw emerge log is kept on disk — press l (or View log on\n"
            "failure) to read it. Esc returns when it finishes.")
