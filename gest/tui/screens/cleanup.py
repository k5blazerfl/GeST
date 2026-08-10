"""Clean Up Packages (urwid): an organized review + removal of orphaned packages.

Instead of dumping raw ``emerge --pretend --depclean --verbose`` (a safety lecture
plus a "pulled in by" block for every *kept* package), the review parses the orphan
list into a table — Category · Package · Version · reclaimable Size — with the
summary counts in a Details panel. Space keeps/removes an individual package.

F10 opens :class:`CleanupRunScreen`, which likewise replaces the raw streaming
removal dump with organized per-package progress (pending → removing → removed /
failed) and a bar, driven by parsing emerge's ``>>> Unmerging (N of M) …`` markers.
The full raw log is spilled to a file and reachable on demand (l / View log).
"""

from __future__ import annotations

import asyncio
import contextlib

import urwid

from gest.core.software import cleanup
from gest.core.software.backend_client import SoftwareBackend
from gest.core.software.cleanup import Orphan, human_size
from gest.tui.runtime import App, Modal, Screen, action_bar
from gest.tui.screens.apply import StreamLog, depclean_plan, remove_plan

_MARK_W = 2   # ✓ = will be removed
_CAT_W = 16
_PKG_W = 22
_VER_W = 22
_SIZE_W = 11

# Per-package removal status glyphs for the run screen.
_STATUS_GLYPH = {"pending": "·", "removing": "▸", "removed": "✓", "failed": "✗"}
_STATUS_ATTR = {"pending": "dim", "removing": None, "removed": "dim",
                "failed": "error"}


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width - 1 else text[: width - 2] + "…"


def _fmt(mark: str, cat: str, pkg: str, ver: str, size: str) -> str:
    return (f"{mark:<{_MARK_W}}{_clip(cat, _CAT_W):<{_CAT_W}}"
            f"{_clip(pkg, _PKG_W):<{_PKG_W}}{_clip(ver, _VER_W):<{_VER_W}}"
            f"{size:>{_SIZE_W}}")


def _orphan_line(o: Orphan, keep: bool) -> str:
    mark = "" if keep else "✓"
    return _fmt(mark, o.category, o.package, o.version, human_size(o.size))


def _row(text: str, attr: str | None = None) -> urwid.Widget:
    icon = urwid.SelectableIcon(text, 0)
    icon.set_wrap_mode("clip")
    return urwid.AttrMap(icon, attr, focus_map="focus")


class CleanupScreen(Screen):
    def __init__(self, app: App) -> None:
        self._plan: cleanup.CleanupPlan | None = None
        self._kept: set[str] = set()   # cp of packages the user chose to keep
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" scanning …")])
        self._list = urwid.ListBox(self._walker)

        header = urwid.AttrMap(
            urwid.Text(_fmt("", "Category", "Package", "Version", "Size"),
                       wrap="clip"),
            "pane_title")
        table = urwid.LineBox(
            urwid.Pile([
                ("pack", header),
                ("pack", urwid.Divider("─")),
                ("weight", 1, self._list),
            ]),
            title="Orphaned packages")

        self._details = urwid.Pile([urwid.Text("")])
        details_box = urwid.LineBox(self._details, title="Details")
        self._count = urwid.Text("")

        body = urwid.Pile([
            ("weight", 1, table),
            ("pack", details_box),
            ("pack", self._count),
            ("pack", action_bar(["Cancel", "Clean up"])),
        ])
        super().__init__(
            app, body, title="Clean Up Packages",
            footer_keys=[
                ("Space", "Keep/Remove"), ("a", "All"), ("n", "None"),
                ("F10", "Clean up"), ("Esc", "Back"),
            ],
            help_text=(
                "Orphaned packages — installed but no longer required by any other\n"
                "installed package or by your @world set. Removing them is safe:\n"
                "depclean never removes a package something still needs.\n\n"
                "Columns:  Category · Package · Version · Size (space reclaimed).\n"
                "A ✓ marks a package for removal (all are marked by default).\n\n"
                "Space  keep / remove the highlighted package\n"
                "a      mark all for removal      n  keep all\n"
                "F10    clean up the marked packages (runs emerge --depclean)\n"
                "Esc    back"
            ),
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        self._kept.clear()
        self._plan = await self.app.run_blocking(cleanup.plan_cleanup)
        self._rebuild()

    # -- rendering ----------------------------------------------------------

    def _orphans(self) -> list[Orphan]:
        return self._plan.orphans if self._plan else []

    def _rebuild(self) -> None:
        focus = self._walker.focus or 0
        plan = self._plan
        if plan is not None and not plan.ok:
            self._walker[:] = [urwid.Text(("error", f" {plan.error}"))]
        elif not self._orphans():
            self._walker[:] = [
                urwid.Text(("ok", " Nothing to clean up — no orphaned packages."))]
        else:
            self._walker[:] = [_row(_orphan_line(o, o.cp in self._kept),
                                    "dim" if o.cp in self._kept else None)
                               for o in self._orphans()]
            self._walker.set_focus(min(focus, len(self._orphans()) - 1))
        self._render_details()
        self._refresh_count()
        self.app.refresh()

    def _render_details(self) -> None:
        rows: list[urwid.Widget]
        if self._plan is None or not self._plan.ok:
            rows = [urwid.Text(("hint", " emerge could not compute a clean-up plan."))]
        else:
            c = self._plan.counts

            def n(key: str) -> str:
                return str(c[key]) if key in c else "—"

            rows = [
                urwid.Text([("field", " "), "No longer required by any installed "
                            "package or your @world set — removal is safe."]),
                urwid.Text([("field", " Installed "), n("installed"),
                            ("field", "   World "), n("world"),
                            ("field", "   System "), n("system")]),
            ]
        self._details.contents = [(w, self._details.options("pack")) for w in rows]

    def _refresh_count(self) -> None:
        orphans = self._orphans()
        if not orphans:
            self._count.set_text(("dim", " No packages to clean up"))
            return
        selected = [o for o in orphans if o.cp not in self._kept]
        size = human_size(sum(o.size for o in selected))
        total = len(orphans)
        if not selected:
            self._count.set_text(("dim", f" Keeping all {total} — nothing marked"))
            return
        scope = (f"{len(selected)} package{'s' if len(selected) != 1 else ''}"
                 if len(selected) == total
                 else f"{len(selected)} of {total} packages")
        self._count.set_text([
            ("ok", f" Clean up {scope}"),
            ("dim", f"   ·   {size} reclaimable   ·   F10 Clean up"),
        ])

    # -- keys ---------------------------------------------------------------

    def _current(self) -> Orphan | None:
        orphans = self._orphans()
        if orphans and 0 <= self._walker.focus < len(orphans):
            return orphans[self._walker.focus]
        return None

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
        elif key == "r":
            self.app.run_async(self._load())
        elif key == " ":
            self._toggle()
        elif key == "a":
            self._kept.clear()
            self._rebuild()
        elif key == "n":
            self._kept = {o.cp for o in self._orphans()}
            self._rebuild()
        elif key == "f10":
            self._clean()
        else:
            return key
        return None

    def _toggle(self) -> None:
        orphan = self._current()
        if orphan is None:
            return
        self._kept.discard(orphan.cp) if orphan.cp in self._kept \
            else self._kept.add(orphan.cp)
        self._rebuild()

    def _clean(self) -> None:
        selected = [o for o in self._orphans() if o.cp not in self._kept]
        if not selected:
            self.app.notify("Nothing marked to clean up.", error=True)
            return
        reload_after = lambda: self.app.run_async(self._load())  # noqa: E731
        if len(selected) == len(self._orphans()):
            plan = depclean_plan()                       # all orphans (bare depclean)
        else:
            plan = remove_plan([o.cp for o in selected])  # just the marked atoms
        self.app.push(CleanupRunScreen(self.app, selected, plan,
                                       on_done=reload_after))


class _Line:
    """One removal-progress row: a seeded orphan (or a cascade package)."""

    __slots__ = ("category", "package", "pf", "size", "status", "version")

    def __init__(self, category, package, version, size, pf):
        self.category, self.package, self.version = category, package, version
        self.size, self.pf, self.status = size, pf, "pending"

    @classmethod
    def from_orphan(cls, o: Orphan) -> _Line:
        return cls(o.category, o.package, o.version, o.size, f"{o.cp}-{o.version}")

    @classmethod
    def from_atom(cls, atom: str) -> _Line:
        cat, _, rest = atom.partition("/")
        return cls(cat, rest, "", 0, atom)


class CleanupRunScreen(StreamLog, Screen):
    """Organized per-package removal progress for `emerge --depclean`.

    Replaces the raw streaming dump: seeds a row per selected orphan and updates
    each row's status live from emerge's ``>>> Unmerging (N of M) …`` markers,
    with a progress bar. The full raw log is spilled to a file (l / View log; and
    auto-offered on failure). Reuses :class:`~gest.tui.screens.apply.StreamLog`.
    """

    def __init__(self, app: App, orphans: list[Orphan], plan, *, on_done=None):
        self._plan = plan
        self._on_done = on_done
        self._lines = [_Line.from_orphan(o) for o in orphans]
        self._by_pf = {ln.pf: ln for ln in self._lines}
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
            urwid.Text(_fmt("", "Category", "Package", "Version", "Size"),
                       wrap="clip"),
            "pane_title")
        table = urwid.LineBox(
            urwid.Pile([("pack", header), ("pack", urwid.Divider("─")),
                        ("weight", 1, self._list)]),
            title="Removing packages")
        body = urwid.Pile([
            ("pack", urwid.AttrMap(self._phase, "field")),
            ("pack", self._bar),
            ("pack", urwid.Divider("─")),
            ("weight", 1, table),
        ])
        super().__init__(
            app, body, title="Clean Up Packages",
            footer_keys=[("l", "View log"), ("Esc", "Back")],
            help_text=(
                "Removing the marked packages with emerge --depclean.\n\n"
                "Each row shows its status:  · pending   ▸ removing   ✓ removed"
                "   ✗ failed\n"
                "The full raw emerge log is kept on disk — press l (or View log on\n"
                "failure) to read it. Esc returns when the removal finishes."
            ),
        )
        self._render()
        app.run_async(self._run())

    # -- rendering ----------------------------------------------------------

    def _render(self) -> None:
        rows = [_row(_fmt(_STATUS_GLYPH[ln.status], ln.category, ln.package,
                          ln.version, human_size(ln.size) if ln.size else ""),
                     _STATUS_ATTR[ln.status])
                for ln in self._lines] or [urwid.Text(" (nothing to remove)")]
        self._walker[:] = rows
        self._schedule_refresh()

    # -- run ----------------------------------------------------------------

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
            self._finish(None, "the removal did not start")
            return
        self._set_phase("Removing packages …")
        await finished.wait()
        await backend.close()
        self._close_log()
        self._finish(code["v"], "")

    def _consume(self, line: str) -> None:
        parsed = cleanup.parse_unmerge(line)
        if parsed is None:
            return
        for ln in self._lines:                 # the prior package is now done
            if ln.status == "removing":
                ln.status = "removed"
        row = self._by_pf.get(parsed.atom)
        if row is None:                        # a dependency cascade beyond the seed
            row = _Line.from_atom(parsed.atom)
            self._lines.append(row)
            self._by_pf[parsed.atom] = row
        row.status = "removing"
        if parsed.total:
            self._total = max(self._total, parsed.total)
            self._bar.done = max(self._total, 1)
        removed = sum(1 for ln in self._lines if ln.status == "removed")
        self._bar.set_completion(min(removed, self._total))
        self._set_phase(f"Removing {parsed.n or removed + 1} of {self._total} — "
                        f"{parsed.atom}")
        self._render()

    def _set_phase(self, text: str, attr: str = "field") -> None:
        self._phase.set_text((attr, f" {text}"))

    def _finish(self, code: int | None, error: str) -> None:
        self._done = True
        ok = code == 0
        if ok:
            for ln in self._lines:
                if ln.status in ("pending", "removing"):
                    ln.status = "removed"
        elif code is not None:
            for ln in self._lines:
                if ln.status == "removing":
                    ln.status = "failed"
        self._bar.set_completion(self._total if ok else self._bar.current)
        self._render()
        if self._on_done is not None and code is not None:
            with contextlib.suppress(Exception):
                self._on_done()
        removed = sum(1 for ln in self._lines if ln.status == "removed")
        freed = human_size(sum(ln.size for ln in self._lines if ln.status == "removed"))
        if code is None:
            reason = error or ("administrator authentication was declined, or the "
                               "backend was unavailable")
            title, msg = "Not started", (
                f"The removal did not start — {reason}. Nothing was changed.")
        elif ok:
            title, msg = "Completed", f"Cleaned up {removed} package(s) · freed {freed}."
        else:
            title, msg = "Failed", (
                f"emerge exited {code}. Some packages may not have been removed; "
                "see the log.")
        self._set_phase(f"Clean up: {title.lower()}", "ok" if ok else "error")
        self._result_modal(title, ok, msg)

    def _result_modal(self, title: str, ok: bool, message: str) -> None:
        self.app.notify(title.lower(), error=not ok)
        if self._logpath:
            message = f"{message}\n\nFull log: {self._logpath}"

        def back():
            self.app.pop()   # the result modal
            self.app.pop()   # the run screen → back to the review

        def view():
            self.app.pop()   # the result modal
            self._view_log()

        modal = Modal(self.app, title,
                      [urwid.Text(("ok" if ok else "error", message))],
                      [("Back", back), ("View log", view)])
        self.app.push_modal(modal, width=("relative", 62), height=("relative", 40))

    def _view_log(self) -> None:
        self.app.push(_RawLogScreen(self.app, self._logpath))

    def handle_key(self, key):
        if key == "esc" and self._done:
            self.app.pop()
        elif key in ("l", "L"):
            self._view_log()
        else:
            return key
        return None


class _RawLogScreen(Screen):
    """A scrollable view of the full raw emerge log (l / View log)."""

    def __init__(self, app: App, path: str | None):
        text = ""
        if path:
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except OSError as exc:
                text = f"(could not read log: {exc})"
        lines = text.splitlines() or ["(the log is empty)"]
        walker = urwid.SimpleFocusListWalker(
            [urwid.Text(ln, wrap="clip") for ln in lines])
        walker.set_focus(len(walker) - 1)   # tail of the log
        super().__init__(
            app, urwid.LineBox(urwid.ListBox(walker), title="emerge log"),
            title="emerge log", footer_keys=[("Esc", "Back")])

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        return key
