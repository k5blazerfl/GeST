"""Shared base for GeST's organized streaming-progress screens.

Clean Up, System Update and Accept each run one or more emerge plans and show a
per-item status table (pending → in-progress → done / failed) over a progress
bar, parse the streamed output to advance each row, and end with a result modal
plus an on-demand raw-log viewer. This captures that shared machinery — the
layout, the backend streaming loop, the settle-and-finish, and the modal/log. A
subclass supplies:

* ``_build_items()`` — the rows (each an object with a ``.status``);
* ``_row_text(item)`` — the formatted table line for a row;
* ``_consume(line)`` — the per-line status machine (parse a marker, mark rows);
* ``_operations()`` — the runnable(s): ``run(backend, on_progress, on_finished)``;
* ``_summary(code)`` — the result ``(title, ok, message)`` for a finished run;

and the class attributes below (glyphs, active/done statuses, titles). Sync
Portage Tree is a review+run hybrid (async-loaded repos, F10-to-start) and keeps
its own screen.
"""

from __future__ import annotations

import asyncio
import contextlib

import urwid

from gest.core.software.backend_client import SoftwareBackend
from gest.tui.runtime import App, Modal, Screen
from gest.tui.screens.apply import RawLogScreen, StreamLog


def clip(text: str, width: int) -> str:
    return text if len(text) <= width - 1 else text[: width - 2] + "…"


def row(text: str, attr: str | None = None) -> urwid.Widget:
    icon = urwid.SelectableIcon(text, 0)
    icon.set_wrap_mode("clip")
    return urwid.AttrMap(icon, attr, focus_map="focus")


class RunScreen(StreamLog, Screen):
    HEADER = ""                 # table column header
    TABLE_TITLE = "Progress"
    SCREEN_TITLE = ""
    RESULT_VERB = ""            # prefixes the finished phase, e.g. "Clean up: done"
    RUN_PHASE = "Working …"
    EMPTY_TEXT = " (nothing to do)"
    STATUS_GLYPH: dict[str, str] = {}
    STATUS_ATTR: dict[str, str | None] = {}
    ACTIVE_STATUSES: tuple[str, ...] = ()   # in-progress statuses, settled at finish
    DONE_STATUS = "done"
    FAIL_STATUS = "failed"

    def __init__(self, app: App, *, on_done=None):
        self._on_done = on_done
        self._done = False
        self._code: int | None = None   # emerge exit code, once finished
        self._logfile = None
        self._logpath: str | None = None
        self._refresh_pending = False
        self._items = list(self._build_items())
        self._total = len(self._items)

        self._walker = urwid.SimpleFocusListWalker([])
        self._list = urwid.ListBox(self._walker)
        self._phase = urwid.Text(("dim", " Preparing …"))
        self._bar = urwid.ProgressBar("pb_normal", "pb_complete", 0, max(self._total, 1))
        header = urwid.AttrMap(urwid.Text(self.HEADER, wrap="clip"), "pane_title")
        table = urwid.LineBox(
            urwid.Pile([("pack", header), ("pack", urwid.Divider("─")),
                        ("weight", 1, self._list)]),
            title=self.TABLE_TITLE)
        body = urwid.Pile([
            ("pack", urwid.AttrMap(self._phase, "field")),
            ("pack", urwid.Divider("─")),
            ("weight", 1, table),
            ("pack", urwid.Divider("─")),
            ("pack", self._bar),
        ])
        super().__init__(app, body, title=self.SCREEN_TITLE,
                         footer_keys=[("l", "View log"), ("Esc", "Back")],
                         help_text=self._help_text())
        self._render()
        app.run_async(self._run())

    # -- hooks (subclass) ---------------------------------------------------

    def _build_items(self):
        raise NotImplementedError

    def _row_text(self, item) -> str:
        raise NotImplementedError

    def _consume(self, line: str) -> None:
        raise NotImplementedError

    def _operations(self):
        raise NotImplementedError

    def _summary(self, code: int):
        raise NotImplementedError

    def _help_text(self) -> str:
        return ""

    # -- rendering ----------------------------------------------------------

    def _render(self) -> None:
        rows = [row(self._row_text(it), self.STATUS_ATTR.get(it.status))
                for it in self._items] or [urwid.Text(self.EMPTY_TEXT)]
        self._walker[:] = rows
        self._schedule_refresh()

    def _glyph(self, status: str) -> str:
        return self.STATUS_GLYPH.get(status, " ")

    def _set_phase(self, text: str, attr: str = "field") -> None:
        self._phase.set_text((attr, f" {text}"))

    def _advance(self) -> int:
        """Repaint from the item statuses; returns the count now DONE_STATUS."""
        done = sum(1 for it in self._items if it.status == self.DONE_STATUS)
        self._bar.set_completion(min(done, self._total))
        self._render()
        return done

    def _grow_total(self, n: int) -> None:
        """Grow the bar denominator (and _total) to at least ``n``."""
        self._total = max(self._total, n)
        self._bar.done = max(self._total, 1)

    def _append(self, item):
        """Add a row discovered mid-run (a dependency cascade). Returns it."""
        self._items.append(item)
        self._grow_total(len(self._items))
        return item

    # -- run ----------------------------------------------------------------

    async def _run(self) -> None:
        self._set_phase(self.RUN_PHASE)
        overall = 0
        aborted = False
        for run_op in self._operations():
            code = await self._run_one(run_op)
            if code is None:
                aborted = True
                break
            overall = overall or code
        self._close_log()
        self._finish(None if aborted else overall)

    async def _run_one(self, run_op):
        finished = asyncio.Event()
        result: dict[str, int | None] = {"code": None}

        def on_progress(lines: list[str]) -> None:
            self._write_log(lines)
            for ln in lines:
                self._consume(ln)

        def on_finished(code: int) -> None:
            result["code"] = code
            finished.set()

        backend = SoftwareBackend()
        try:
            await backend.connect()
            started = await run_op(backend, on_progress, on_finished)
        except Exception:
            with contextlib.suppress(Exception):
                await backend.close()
            return None
        if not started:
            await backend.close()
            return None
        await finished.wait()
        await backend.close()
        return result["code"]

    def _finish(self, code: int | None) -> None:
        self._done = True
        self._code = code
        if code == 0:
            for it in self._items:
                if it.status == "pending" or it.status in self.ACTIVE_STATUSES:
                    it.status = self.DONE_STATUS
        elif code is not None:
            for it in self._items:
                if it.status in self.ACTIVE_STATUSES:
                    it.status = self.FAIL_STATUS
        self._bar.set_completion(self._total if code == 0 else self._bar.current)
        self._render()
        if self._on_done is not None and code is not None:
            with contextlib.suppress(Exception):
                self._on_done()
        if code is None:
            title, ok, msg = "Not started", False, (
                "The operation did not start — administrator authentication was "
                "declined, or the backend was unavailable. Nothing was changed.")
        else:
            title, ok, msg = self._summary(code)
        prefix = f"{self.RESULT_VERB}: " if self.RESULT_VERB else ""
        self._set_phase(f"{prefix}{title.lower()}", "ok" if ok else "error")
        self._present_result(title, ok, msg)

    def _present_result(self, title: str, ok: bool, message: str) -> None:
        """How a finished run concludes. Default shows the result modal; a
        subclass may override to insert a follow-up step first (e.g. an
        uninstall handing straight over to Clean Up)."""
        self._result_modal(title, ok, message)

    def _result_modal(self, title: str, ok: bool, message: str) -> None:
        self.app.notify(title.lower(), error=not ok)
        if self._logpath:
            message = f"{message}\n\nFull log: {self._logpath}"

        def back():
            self.app.pop()   # the result modal
            self.app.pop()   # the run screen → back to the caller

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
