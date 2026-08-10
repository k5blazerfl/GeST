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

import asyncio
import contextlib

import urwid

from gest.core.software import update
from gest.core.software.backend_client import SoftwareBackend
from gest.core.software.update import Change, human_size
from gest.tui.runtime import App, Modal, Screen, action_bar
from gest.tui.screens.apply import RawLogScreen, StreamLog, world_plan

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


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width - 1 else text[: width - 2] + "…"


def _fmt(glyph: str, cat: str, pkg: str, change: str, dl: str) -> str:
    return (f"{glyph:<{_GLYPH_W}}{_clip(cat, _CAT_W):<{_CAT_W}}"
            f"{_clip(pkg, _PKG_W):<{_PKG_W}}{_clip(change, _CHANGE_W):<{_CHANGE_W}}"
            f"{dl:>{_DL_W}}")


def _change_text(c: Change) -> str:
    change = f"{c.old_version} → {c.new_version}" if c.action == update.UPDATE \
        else c.new_version
    return f"{change}  (bin)" if c.binary else change


def _row_line(c: Change) -> str:
    return _fmt(_ACTION_GLYPH.get(c.action, " "), c.category, c.package,
               _change_text(c), human_size(c.size))


def _row(text: str, attr: str | None = None) -> urwid.Widget:
    icon = urwid.SelectableIcon(text, 0)
    icon.set_wrap_mode("clip")
    return urwid.AttrMap(icon, attr, focus_map="focus")


class UpdateScreen(Screen):
    def __init__(self, app: App) -> None:
        self._plan: update.UpdatePlan | None = None
        self._walker = urwid.SimpleFocusListWalker(
            [urwid.Text(" computing the update plan …  (this can take a while)")])
        self._list = urwid.ListBox(self._walker)

        header = urwid.AttrMap(
            urwid.Text(_fmt("", "Category", "Package", "Change", "Download"),
                       wrap="clip"),
            "pane_title")
        table = urwid.LineBox(
            urwid.Pile([("pack", header), ("pack", urwid.Divider("─")),
                        ("weight", 1, self._list)]),
            title="Packages to update")

        self._details = urwid.Pile([urwid.Text("")])
        details_box = urwid.LineBox(self._details, title="Details")
        self._count = urwid.Text("")

        body = urwid.Pile([
            ("weight", 1, table),
            ("pack", details_box),
            ("pack", self._count),
            ("pack", action_bar(["Cancel", "Update"])),
        ])
        super().__init__(
            app, body, title="System Update",
            footer_keys=[("F10", "Update"), ("r", "Reload"), ("Esc", "Back")],
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
        app.run_async(self._load())

    async def _load(self) -> None:
        self._plan = await self.app.run_blocking(update.plan_update)
        self._rebuild()

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
            self._walker[:] = [_row(_row_line(c)) for c in self._changes()]
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
                    "   ·   F10 Update"),
        ])

    # -- keys ---------------------------------------------------------------

    def handle_key(self, key):
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


class UpdateRunScreen(StreamLog, Screen):
    """Organized per-package progress for ``emerge -uDN @world``.

    Replaces the raw streaming dump: a row per package to update, its status
    advancing live from emerge's ``>>> Emerging/Installing (N of M) …`` markers
    (pending → building → installed / failed) with a progress bar. The full raw
    log is spilled to a file (l / View log; auto-offered on failure).
    """

    def __init__(self, app: App, changes: list[Change], plan, *, on_done=None):
        self._plan = plan
        self._on_done = on_done
        self._lines = [_RunLine.from_change(c) for c in changes]
        self._by_cp = {ln.cp: ln for ln in self._lines}
        self._total = len(self._lines)
        self._done = False
        self._logfile = None
        self._logpath: str | None = None
        self._refresh_pending = False

        self._walker = urwid.SimpleFocusListWalker([])
        self._list = urwid.ListBox(self._walker)
        self._phase = urwid.Text(("dim", " Preparing …"))
        self._bar = urwid.ProgressBar("pb_normal", "pb_complete", 0, max(self._total, 1))

        header = urwid.AttrMap(
            urwid.Text(_fmt("", "Category", "Package", "Change", ""), wrap="clip"),
            "pane_title")
        table = urwid.LineBox(
            urwid.Pile([("pack", header), ("pack", urwid.Divider("─")),
                        ("weight", 1, self._list)]),
            title="Updating packages")
        body = urwid.Pile([
            ("pack", urwid.AttrMap(self._phase, "field")),
            ("pack", self._bar),
            ("pack", urwid.Divider("─")),
            ("weight", 1, table),
        ])
        super().__init__(
            app, body, title="System Update",
            footer_keys=[("l", "View log"), ("Esc", "Back")],
            help_text=(
                "Running emerge -uDN @world.\n\n"
                "Each row shows its status:  · pending   ▸ building   ✓ installed"
                "   ✗ failed\n"
                "The full raw emerge log is kept on disk — press l (or View log on\n"
                "failure) to read it. Esc returns when the update finishes."
            ),
        )
        self._render()
        app.run_async(self._run())

    def _render(self) -> None:
        rows = [_row(_fmt(_RUN_GLYPH[ln.status], ln.category, ln.package,
                          ln.change, ""), _RUN_ATTR[ln.status])
                for ln in self._lines] or [urwid.Text(" (nothing to update)")]
        self._walker[:] = rows
        self._schedule_refresh()

    def _set_phase(self, text: str, attr: str = "field") -> None:
        self._phase.set_text((attr, f" {text}"))

    async def _run(self) -> None:
        finished = asyncio.Event()
        code: dict[str, int | None] = {"v": None}

        def on_progress(lines: list[str]) -> None:
            self._write_log(lines)
            for ln in lines:
                self._consume(ln)

        def on_finished(exit_code: int) -> None:
            code["v"] = exit_code
            finished.set()

        backend = SoftwareBackend()
        try:
            await backend.connect()
            started = await self._plan.run(backend, on_progress, on_finished)
        except Exception as exc:
            with contextlib.suppress(Exception):
                await backend.close()
            self._finish(None, str(exc))
            return
        if not started:
            await backend.close()
            self._finish(None, "the update did not start")
            return
        self._set_phase("Updating packages …")
        await finished.wait()
        await backend.close()
        self._close_log()
        self._finish(code["v"], "")

    def _consume(self, line: str) -> None:
        p = update.parse_merge_progress(line)
        if p is None:
            return
        cp, _ = update.split_cpv(p.atom)
        row = self._by_cp.get(cp)
        if row is None:                        # a dependency not in the pretend plan
            row = _RunLine.from_cp(cp)
            self._lines.append(row)
            self._by_cp[cp] = row
        row.status = "building" if p.phase == "Emerging" else "installed"
        if p.total:
            self._total = max(self._total, p.total)
            self._bar.done = max(self._total, 1)
        installed = sum(1 for r in self._lines if r.status == "installed")
        self._bar.set_completion(min(installed, self._total))
        self._set_phase(f"{p.phase} {p.n} of {self._total} — {p.atom}")
        self._render()

    def _finish(self, code: int | None, error: str) -> None:
        self._done = True
        ok = code == 0
        if ok:
            for ln in self._lines:
                if ln.status in ("pending", "building"):
                    ln.status = "installed"
        elif code is not None:
            for ln in self._lines:
                if ln.status == "building":
                    ln.status = "failed"
        self._bar.set_completion(self._total if ok else self._bar.current)
        self._render()
        if self._on_done is not None and code is not None:
            with contextlib.suppress(Exception):
                self._on_done()
        done = sum(1 for ln in self._lines if ln.status == "installed")
        if code is None:
            reason = error or ("administrator authentication was declined, or the "
                               "backend was unavailable")
            title, msg = "Not started", (
                f"The update did not start — {reason}. Nothing was changed.")
        elif ok:
            title, msg = "Completed", f"Updated {done} package(s)."
        else:
            title, msg = "Failed", (
                f"emerge exited {code}. The update may be incomplete; see the log.")
        self._set_phase(f"System update: {title.lower()}", "ok" if ok else "error")
        self._result_modal(title, ok, msg)

    def _result_modal(self, title: str, ok: bool, message: str) -> None:
        self.app.notify(title.lower(), error=not ok)
        if self._logpath:
            message = f"{message}\n\nFull log: {self._logpath}"

        def back():
            self.app.pop()   # the result modal
            self.app.pop()   # the run screen → back to the review

        def view():
            self.app.pop()
            self._view_log()

        modal = Modal(self.app, title,
                      [urwid.Text(("ok" if ok else "error", message))],
                      [("Back", back), ("View log", view)])
        self.app.push_modal(modal, width=("relative", 62), height=("relative", 40))

    def _view_log(self) -> None:
        self.app.push(RawLogScreen(self.app, self._logpath))

    def handle_key(self, key):
        if key == "esc" and self._done:
            self.app.pop()
        elif key in ("l", "L"):
            self._view_log()
        else:
            return key
        return None
