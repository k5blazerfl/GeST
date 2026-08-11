"""System logs (urwid): two-pane source list | scrollable ANSI pager.

Read-only. Reads dmesg / the boot log / readable /var/log files off the UI
thread; line colour is rendered with the shared ANSI markup helper.
"""

from __future__ import annotations

import urwid

from gest.core.logs import reader
from gest.core.logs.model import LogSource
from gest.tui.runtime import App, Screen, ansi_markup, boxed


def _src_row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


def _log_line(raw: str) -> urwid.Widget:
    icon = urwid.SelectableIcon(ansi_markup(raw), 0)
    icon.set_wrap_mode("clip")
    return icon


class LogsScreen(Screen):
    def __init__(self, app: App) -> None:
        self._sources: list[LogSource] = []
        self._src_walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._left = urwid.ListBox(self._src_walker)
        self._view_walker = urwid.SimpleFocusListWalker([])
        self._right = urwid.ListBox(self._view_walker)
        self._columns = urwid.Columns(
            [(30, boxed(self._left, title="Logs")),
             boxed(self._right, title="View")],
            dividechars=1,
        )
        super().__init__(
            app, self._columns, title="System Logs",
            footer_keys=[("Enter", "View"), ("→", "Pager"),
                         ("r", "Refresh"), ("Esc", "Back")],
            help_text=(
                "Read-only viewer for system logs.\n\n"
                "Left: pick a source (dmesg, the OpenRC boot log, or a readable\n"
                "file under /var/log). →/Enter moves to the pager; ↑/↓ scroll.\n"
                "r reloads the current source. Esc steps back.\n\n"
                "Sources needing root (restricted dmesg, root-only files) show a\n"
                "note instead of content — run GeST's viewer as root to see them."
            ),
        )
        urwid.connect_signal(self._src_walker, "modified", self._on_source)
        app.run_async(self._load_sources())

    async def _load_sources(self) -> None:
        sources = await self.app.run_blocking(reader.list_sources)
        self._sources = sources
        self._src_walker[:] = [_src_row(s.label) for s in sources] or \
            [urwid.Text(" (no readable logs)")]
        if sources:
            self._src_walker.set_focus(0)  # fires _on_source → loads the view
        self.app.refresh()

    def _current(self) -> LogSource | None:
        if not self._sources:
            return None
        idx = self._src_walker.focus
        if idx is None or not 0 <= idx < len(self._sources):
            return None
        return self._sources[idx]

    def _on_source(self) -> None:
        source = self._current()
        if source is not None:
            self.app.run_async(self._load_view(source))

    async def _load_view(self, source: LogSource) -> None:
        lines = await self.app.run_blocking(reader.read_source, source)
        self._view_walker[:] = [_log_line(line) for line in lines] or \
            [urwid.Text(" (empty)")]
        self._view_walker.set_focus(len(self._view_walker) - 1)  # tail
        self.app.refresh()

    def handle_key(self, key):
        if key == "esc":
            if self._columns.focus_position == 1:
                self._columns.focus_position = 0
            else:
                self.app.pop()
            return None
        if key in ("enter", "right") and self._columns.focus_position == 0:
            self._columns.focus_position = 1
            return None
        if key == "r":
            source = self._current()
            if source is not None:
                self.app.run_async(self._load_view(source))
            return None
        return key
