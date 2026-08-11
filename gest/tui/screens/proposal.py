"""Software Management proposal (urwid): a YaST-style resolved review before Accept.

Pressing F10 (Accept) doesn't apply the marks straight away — it first resolves
what emerge would actually do (``emerge --pretend`` for the installs, and the
depclean pass for the removals), then shows the full plan: every package to
install/update (including dependencies pulled in) and to remove, with the
version change and download size, plus the totals. F10 applies the proposal
(hands over to :class:`AcceptRunScreen`); Esc cancels back to the package list.
"""

from __future__ import annotations

import urwid

from gest.core.software import cleanup, preview, update
from gest.core.software.update import human_size
from gest.tui.runtime import App, NavPile, Screen, boxed, focusable_actions
from gest.tui.screens.accept import AcceptRunScreen
from gest.tui.screens.runscreen import clip, row

_G_W, _CAT_W, _PKG_W, _CHG_W, _SZ_W = 2, 16, 24, 22, 11

# Lead glyph + colour per action.  + new · ↑ update · ⟳ rebuild · - remove.
_ACTION_GLYPH = {update.NEW: "+", update.UPDATE: "↑", update.REBUILD: "⟳"}
_ACTION_ATTR = {update.NEW: "ok", update.UPDATE: "field", update.REBUILD: "dim"}


def _fmt(glyph: str, cat: str, pkg: str, chg: str, sz: str) -> str:
    return (f"{glyph:<{_G_W}}{clip(cat, _CAT_W):<{_CAT_W}}"
            f"{clip(pkg, _PKG_W):<{_PKG_W}}{clip(chg, _CHG_W):<{_CHG_W}}"
            f"{sz:>{_SZ_W}}")


class _Item:
    """One proposal row: an install/update change or a removal."""

    __slots__ = ("attr", "category", "change", "glyph", "package", "size")

    def __init__(self, glyph, attr, category, package, change, size):
        self.glyph, self.attr = glyph, attr
        self.category, self.package = category, package
        self.change, self.size = change, size


def _from_change(c) -> _Item:
    change = (f"{c.old_version} → {c.new_version}" if c.action == update.UPDATE
              else c.new_version)
    if c.binary:
        change += "  (bin)"
    return _Item(_ACTION_GLYPH.get(c.action, " "), _ACTION_ATTR.get(c.action),
                 c.category, c.package, change, c.size)


def _from_orphan(o) -> _Item:
    return _Item("-", "error", o.category, o.package, o.version, o.size)


class ProposalScreen(Screen):
    """Resolved review of the marked changes, shown before they are applied."""

    def __init__(self, app: App, *, installs=(), binpkgs=(), binprefs=(),
                 removes=(), on_done=None):
        self._installs = list(installs)
        self._binpkgs = list(binpkgs)
        self._binprefs = list(binprefs)
        self._removes = list(removes)
        self._on_done = on_done
        self._items: list[_Item] = []
        self._n_install = 0
        self._n_remove = 0
        self._download = 0
        self._freed = 0
        self._error = ""
        self._ready = False

        self._walker = urwid.SimpleFocusListWalker(
            [urwid.Text(" Computing the proposal …  (resolving with emerge)")])
        self._list = urwid.ListBox(self._walker)
        header = urwid.AttrMap(
            urwid.Text(_fmt("", "Category", "Package", "Change", "Size"),
                       wrap="clip"), "pane_title")
        table = boxed(
            urwid.Pile([("pack", header), ("pack", urwid.Divider("─")),
                        ("weight", 1, self._list)]),
            title="Proposal")
        self._phase = urwid.Text(("dim", " Resolving …"))
        self._totals = urwid.Text("")
        self._actions = focusable_actions([
            ("Cancel", app.pop), ("Apply", self._apply)])
        body = NavPile([
            ("pack", urwid.AttrMap(self._phase, "field")),
            ("pack", urwid.Divider("─")),
            ("weight", 1, table),
            ("pack", self._totals),
            ("pack", self._actions),
        ])
        super().__init__(
            app, body, title="Software Management",
            footer_keys=[("F10", "Apply"), ("Esc", "Cancel")],
            help_text=(
                "The resolved proposal — what emerge would actually do for the\n"
                "packages you marked, including dependencies pulled in and any\n"
                "packages removed as a consequence.\n\n"
                "Lead glyph:  + new   ↑ update   ⟳ rebuild   - remove.\n"
                "F10 applies the proposal; Esc cancels back to the package list."))
        self.configure_pane_cycle(body, [2], action_row=self._actions)
        app.run_async(self._compute())

    def _footer_context(self):
        if self._on_action_row():
            return [("Enter", "Activate"), ("Tab", "Next"), ("Esc", "Cancel")]
        return self._base_footer_keys

    # -- resolve ------------------------------------------------------------

    async def _compute(self) -> None:
        changes: list = []
        orphans: list = []
        errors: list[str] = []

        async def step(phase, fn):
            self._set_phase(phase)
            r = await self.app.run_blocking(fn)
            if not r.ok:
                errors.append(r.summary)
            return r

        if self._installs:
            r = await step("Resolving installs …",
                           lambda: preview.preview_install_many(self._installs))
            changes += update.parse_changes(r.output)
        if self._binpkgs:
            r = await step("Resolving binary installs …",
                           lambda: preview.preview_install_binary_many(
                               self._binpkgs, only=True))
            changes += update.parse_changes(r.output)
        if self._binprefs:
            r = await step("Resolving installs (prefer binary) …",
                           lambda: preview.preview_install_binary_many(
                               self._binprefs, only=False))
            changes += update.parse_changes(r.output)
        if self._removes:
            r = await step("Resolving removals …",
                           lambda: preview.preview_depclean_many(self._removes))
            orphans += cleanup.parse_orphans(r.output)

        self._items = ([_from_change(c) for c in changes]
                       + [_from_orphan(o) for o in orphans])
        self._n_install = len(changes)
        self._n_remove = len(orphans)
        self._download = sum(c.size for c in changes)
        self._freed = sum(o.size for o in orphans)
        self._error = "  ·  ".join(e for e in errors if e)
        self._ready = True
        self._render()

    # -- render -------------------------------------------------------------

    def _set_phase(self, text: str, attr: str = "field") -> None:
        self._phase.set_text((attr, f" {text}"))
        self.app.refresh()

    def _render(self) -> None:
        if self._items:
            self._walker[:] = [
                row(_fmt(it.glyph, it.category, it.package, it.change,
                         human_size(it.size) if it.size else ""), it.attr)
                for it in self._items]
            self._walker.set_focus(0)
        else:
            msg = self._error or "Nothing to do — no changes to apply."
            self._walker[:] = [urwid.Text(("error" if self._error else "ok",
                                           f" {msg}"))]

        if self._error:
            self._set_phase("Resolution reported problems — review below.", "error")
        elif self._items:
            self._set_phase("Proposal ready — F10 to apply, Esc to cancel.", "ok")
        else:
            self._set_phase("Nothing to do.", "dim")

        parts: list = []
        if self._n_install:
            parts.append(("ok", f" Install {self._n_install}"))
        if self._n_remove:
            parts.append(("error", f"   Remove {self._n_remove}"))
        if self._download:
            parts.append(("dim", f"   Download {human_size(self._download)}"))
        if self._freed:
            parts.append(("dim", f"   Frees {human_size(self._freed)}"))
        self._totals.set_text(parts or [("dim", " No changes")])
        self.app.refresh()

    # -- keys ---------------------------------------------------------------

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()                       # cancel → back to the package list
            return None
        if key == "f10":
            self._apply()
            return None
        return key

    def _apply(self) -> None:
        if not self._ready:
            self.app.notify("Still computing the proposal …")
            return
        if not self._items:
            self.app.notify("Nothing to apply.")
            return
        # Swap the proposal for the live run so Back/Package Manager from the run
        # returns to the package list, not to this (spent) proposal.
        self.app.replace(AcceptRunScreen(
            self.app, installs=self._installs, binpkgs=self._binpkgs,
            binprefs=self._binprefs, removes=self._removes,
            on_done=self._on_done))
