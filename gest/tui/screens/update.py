"""System Update (urwid): an organized review of what a world update would do.

Instead of the raw ``emerge --pretend -uDN @world`` dump (the ``[ebuild …]`` list
buried in dependency-resolution noise), this parses it into a compact table —
action · Category · Package · version change · download size — with the totals in
a Details panel. F10 opens :class:`UpdateRunScreen`, which likewise replaces the
raw streaming dump with organized per-package progress (pending → building →
installed / failed) driven by emerge's ``>>> Emerging/Installing (N of M) …``
markers; the raw log stays reachable (l / View log).
"""

from __future__ import annotations

import urwid

from gest.core import prefs
from gest.core.software import update
from gest.core.software.update import Change, human_size
from gest.tui.runtime import App, NavPile, Screen, boxed, focusable_actions
from gest.tui.screens.apply import world_plan
from gest.tui.screens.autoaccept import AutoAccept
from gest.tui.screens.loading import LoadingScreen
from gest.tui.screens.runscreen import RunScreen, clip, row

_GLYPH_W = 2
_CAT_W = 14
_PKG_W = 22
_CHANGE_W = 24
_DL_W = 11

# Action → lead glyph.  + new · ↑ update · ⟳ rebuild/reinstall.
_ACTION_GLYPH = {update.NEW: "+", update.UPDATE: "↑", update.REBUILD: "⟳"}

# Per-package run status → glyph / attr.
_RUN_GLYPH = {"pending": "·", "building": "▸", "installed": "✓", "failed": "✗"}
_RUN_ATTR = {"pending": "dim", "building": None, "installed": "dim",
             "failed": "error"}


def _fmt(glyph: str, cat: str, pkg: str, change: str, dl: str) -> str:
    return (f"{glyph:<{_GLYPH_W}}{clip(cat, _CAT_W):<{_CAT_W}}"
            f"{clip(pkg, _PKG_W):<{_PKG_W}}{clip(change, _CHANGE_W):<{_CHANGE_W}}"
            f"{dl:>{_DL_W}}")


def _change_text(c: Change) -> str:
    change = f"{c.old_version} → {c.new_version}" if c.action == update.UPDATE \
        else c.new_version
    return f"{change}  (bin)" if c.binary else change


def _row_line(c: Change) -> str:
    return _fmt(_ACTION_GLYPH.get(c.action, " "), c.category, c.package,
               _change_text(c), human_size(c.size))


class UpdateScreen(AutoAccept, Screen):
    _auto_action = "Updating"

    def __init__(self, app: App, preloaded: update.UpdatePlan | None = None,
                 *, auto: bool = True) -> None:
        # ``preloaded`` lets UpdateLoadingScreen hand over an already-resolved
        # plan so we don't run emerge --pretend @world twice. ``auto`` is False
        # when the loading screen already ran the accept-mode policy (manual
        # review only — don't re-arm a countdown here).
        self._plan: update.UpdatePlan | None = preloaded
        self._auto = auto
        self._armed = False
        self._walker = urwid.SimpleFocusListWalker(
            [urwid.Text(" computing the update plan …  (this can take a while)")])
        self._list = urwid.ListBox(self._walker)

        header = urwid.AttrMap(
            urwid.Text(_fmt("", "Category", "Package", "Change", "Download"),
                       wrap="clip"),
            "pane_title")
        table = boxed(
            urwid.Pile([("pack", header), ("pack", urwid.Divider("─")),
                        ("weight", 1, self._list)]),
            title="Packages to update")

        self._details = urwid.Pile([urwid.Text("")])
        details_box = boxed(self._details, title="Details")
        self._count = urwid.Text("")

        self._actions = focusable_actions([
            ("Cancel", app.pop), ("Accept", self._update)])
        body = NavPile([
            ("weight", 1, table),
            ("pack", details_box),
            ("pack", self._count),
            ("pack", self._actions),
        ])
        super().__init__(
            app, body, title="System Update",
            footer_keys=[("F10", "Accept"), ("r", "Reload"), ("Esc", "Back")],
            help_text=(
                "A full system update — everything reachable from @world that has a\n"
                "newer version (or changed USE), updated together (deep, new-use).\n\n"
                "Columns:  Category · Package · Change (old → new version) · Download.\n"
                "Lead glyph:  + new dependency   ↑ update   ⟳ rebuild/reinstall\n"
                "(bin) marks a binary package. The Details panel totals the run.\n\n"
                "A world update is applied as a whole (F10) — review it here, then\n"
                "F10 runs emerge -uDN @world.   r reloads the plan.   Esc goes back."
            ),
        )
        self.configure_pane_cycle(body, [0], action_row=self._actions)
        if preloaded is not None:
            self._rebuild()                         # plan already resolved
            app.run_async(self._arm_when_ready())   # after the caller pushes us
        else:
            app.run_async(self._load())

    async def _arm_when_ready(self) -> None:
        self._maybe_arm()

    def _footer_context(self):
        if self._timer_running:
            return [("Enter", "Update now"), ("Esc", "Stop")]
        if self._on_action_row():
            return [("Enter", "Activate"), ("Tab", "Next"), ("Esc", "Back")]
        return self._base_footer_keys

    # -- auto-accept (AutoAccept hooks) -------------------------------------

    def _auto_apply(self) -> None:
        self._update()

    def _auto_set_status(self, markup) -> None:
        self._count.set_text(markup)

    def _maybe_arm(self) -> None:
        # Arm once, only when there's actually something to update. An empty or
        # failed plan is reviewed manually; reloads (r) don't re-arm. When the
        # loading screen already ran the policy (auto=False), never re-arm.
        if self._armed or not self._auto:
            return
        if self._plan is not None and self._plan.ok and self._changes():
            self._armed = True
            self.arm_auto_accept()

    async def _load(self) -> None:
        self._plan = await self.app.run_blocking(update.plan_update)
        self._rebuild()
        self._maybe_arm()

    # -- rendering ----------------------------------------------------------

    def _changes(self) -> list[Change]:
        return self._plan.changes if self._plan else []

    def _rebuild(self) -> None:
        plan = self._plan
        if plan is not None and not plan.ok:
            self._walker[:] = [urwid.Text(("error", f" {plan.error}"))]
        elif not self._changes():
            self._walker[:] = [
                urwid.Text(("ok", " Nothing to update — the system is up to date."))]
        else:
            self._walker[:] = [row(_row_line(c)) for c in self._changes()]
            self._walker.set_focus(0)
        self._render_details()
        self._refresh_count()
        self.app.refresh()

    def _render_details(self) -> None:
        if self._plan is None or not self._plan.ok:
            rows = [urwid.Text(("hint", " emerge could not compute an update plan."))]
        else:
            c = self._plan.counts()
            rows = [urwid.Text([
                ("field", " Updates "), str(c[update.UPDATE]),
                ("field", "   New "), str(c[update.NEW]),
                ("field", "   Rebuilds "), str(c[update.REBUILD]),
                ("field", "   Download "), human_size(self._plan.total_download),
            ])]
        self._details.contents = [(w, self._details.options("pack")) for w in rows]

    def _refresh_count(self) -> None:
        n = len(self._changes())
        if not n:
            self._count.set_text(("dim", " No packages to update"))
            return
        self._count.set_text([
            ("ok", f" {n} package{'s' if n != 1 else ''} to update"),
            ("dim", f"   ·   {human_size(self._plan.total_download)} download"
                    "   ·   F10 Accept"),
        ])

    # -- keys ---------------------------------------------------------------

    def handle_key(self, key):
        outcome = self._auto_key(key)            # Enter/F10 update now · Esc stop
        if outcome == "applied":
            return None
        if outcome == "stopped":                 # keep reviewing, back to manual
            self._refresh_count()
            self._refresh_footer()
            return None
        if self._timer_running and key == "r":
            self._timer_running = False          # recomputing → cancel the auto-run
            self._refresh_footer()
        if key == "esc":
            self.app.pop()
        elif key == "r":
            self._walker[:] = [urwid.Text(" recomputing the update plan …")]
            self.app.run_async(self._load())
        elif key == "f10":
            self._update()
        else:
            return key
        return None

    def _update(self) -> None:
        if self._plan is None or not self._plan.ok or not self._changes():
            self.app.notify("Nothing to update.")
            return
        self.app.push(UpdateRunScreen(
            self.app, self._changes(), world_plan(),
            on_done=lambda: self.app.run_async(self._load())))


class _RunLine:
    """One update-progress row: a seeded change (or a cascade package)."""

    __slots__ = ("category", "change", "cp", "package", "status")

    def __init__(self, category, package, change, cp):
        self.category, self.package, self.change, self.cp = category, package, change, cp
        self.status = "pending"

    @classmethod
    def from_change(cls, c: Change) -> _RunLine:
        return cls(c.category, c.package, _change_text(c), c.cp)

    @classmethod
    def from_cp(cls, cp: str) -> _RunLine:
        cat, _, pkg = cp.partition("/")
        return cls(cat, pkg or cp, "", cp)


class UpdateRunScreen(RunScreen):
    """Organized per-package progress for ``emerge -uDN @world`` (Emerging/Installing)."""

    HEADER = _fmt("", "Category", "Package", "Change", "")
    TABLE_TITLE = "Updating packages"
    SCREEN_TITLE = "System Update"
    RESULT_VERB = "System update"
    RUN_PHASE = "Updating packages …"
    EMPTY_TEXT = " (nothing to update)"
    STATUS_GLYPH = _RUN_GLYPH
    STATUS_ATTR = _RUN_ATTR
    ACTIVE_STATUSES = ("building",)
    DONE_STATUS = "installed"
    BRAND_SUBTITLE = "Updating packages"

    def __init__(self, app: App, changes: list[Change], plan, *, on_done=None,
                 branded=False):
        self._changes = changes
        self._plan = plan
        super().__init__(app, on_done=on_done, branded=branded)

    def _build_items(self):
        items = [_RunLine.from_change(c) for c in self._changes]
        self._by_cp = {it.cp: it for it in items}
        return items

    def _row_text(self, it) -> str:
        return _fmt(self._glyph(it.status), it.category, it.package, it.change, "")

    def _operations(self):
        return [self._plan.run]

    def _consume(self, line: str) -> None:
        p = update.parse_merge_progress(line)
        if p is None:
            return
        cp, _ = update.split_cpv(p.atom)
        line = self._by_cp.get(cp)
        if line is None:                       # a dependency not in the pretend plan
            line = _RunLine.from_cp(cp)
            self._append(line)
            self._by_cp[cp] = line
        line.status = "building" if p.phase == "Emerging" else "installed"
        if p.total:
            self._grow_total(p.total)
        self._set_phase(f"{p.phase} {p.n} of {self._total} — {p.atom}")
        self._advance()

    def _summary(self, code: int):
        done = sum(1 for it in self._items if it.status == "installed")
        if code == 0:
            return "Completed", True, f"Updated {done} package(s)."
        return "Failed", False, (
            f"emerge exited {code}. The update may be incomplete; see the log.")

    def _help_text(self) -> str:
        return (
            "Running emerge -uDN @world.\n\n"
            "Each row shows its status:  · pending   ▸ building   ✓ installed"
            "   ✗ failed\n"
            "The full raw emerge log is kept on disk — press l (or View log on\n"
            "failure) to read it. Esc returns when the update finishes.")


class UpdateLoadingScreen(AutoAccept, LoadingScreen):
    """Fullscreen resolve + auto-accept for System Update.

    Resolving a world update (``emerge --pretend -uDN @world``) can take a while
    on a large system, so show the branded loading screen while it resolves. When
    it resolves cleanly with changes, apply the accept-mode policy right here —
    update at once (immediate), count down on the branded screen (timer; Enter
    updates now / Esc reviews), or hand off to :class:`UpdateScreen` (manual). An
    up-to-date system or a failed resolve opens the review so the user reads the
    message.
    """

    _auto_action = "Updating"

    def __init__(self, app: App) -> None:
        self._plan = None
        super().__init__(
            app,
            [{"key": "resolve", "label": "Resolve the world update",
              "status": "pending", "detail": ""}],
            title="System Update",
            subtitle="Computing the system update",
            help_text=(
                "Resolving what a full @world update would do "
                "(emerge --pretend -uDN\n@world) — this can take a while on a "
                "large system.\nWhen there is something to update it applies per "
                "your accept-mode preference:\n"
                "  · immediate — updates at once\n"
                "  · timer — counts down here; Enter updates now, Esc reviews\n"
                "  · manual — opens the review to confirm\n"
                "Esc cancels and returns to the main menu."))

    async def _run(self) -> None:
        self._set_step("resolve", "active")
        self._set_phase("Running emerge --pretend -uDN @world …  "
                        "(this can take a while)")
        plan = await self.app.run_blocking(update.plan_update)
        self._plan = plan
        if plan is None or not plan.ok:
            self._set_step("resolve", "failed")
            self._bar.set_completion(1)
            self._to_review()                    # show the failure in the review
            return
        n = len(plan.changes)
        self._set_step("resolve", "done", f"{n} change{'s' if n != 1 else ''}")
        # Nothing to update, or the user reviews every plan: open the review.
        # Otherwise apply the accept-mode policy here — immediate updates at once,
        # timer counts down on this branded screen.
        if not plan.changes or prefs.accept_mode() == prefs.MANUAL:
            self._bar.set_completion(1)
            self._to_review()
        else:
            self._set_phase("Ready.", "ok")
            self.arm_auto_accept()

    # -- auto-accept (AutoAccept hooks) -------------------------------------

    def _auto_progress(self, remaining: int, frac: float) -> None:
        self._bar.set_completion(frac)
        self._set_phase(f"{self._auto_action} in {remaining}s — "
                        "Enter updates now, Esc reviews.", "ok")

    def _auto_apply(self) -> None:
        # Applied without a review (immediate / timed): run the world update and
        # keep the branded look going into the run.
        if not (self.app._stack and self.app._stack[-1] is self):   # cancelled
            return
        self.app.replace(UpdateRunScreen(
            self.app, self._plan.changes, world_plan(), branded=True))

    def _to_review(self) -> None:
        if self.app._stack and self.app._stack[-1] is self:         # not cancelled
            self.app.replace(UpdateScreen(self.app, preloaded=self._plan,
                                          auto=False))

    # -- keys / footer ------------------------------------------------------

    def _footer_context(self):
        if self._timer_running:
            return [("Enter", "Update now"), ("Esc", "Review")]
        return self._base_footer_keys

    def handle_key(self, key):
        outcome = self._auto_key(key)            # Enter/F10 update now · Esc review
        if outcome == "applied":
            return None
        if outcome == "stopped":                 # Esc during countdown → review
            self._to_review()
            return None
        if key == "esc":
            self.app.pop()                       # cancel resolve → back to the menu
            return None
        return key
