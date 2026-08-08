"""Portage news viewer (urwid): list items, read content. Read-only."""

from __future__ import annotations

import urwid

from gest.core.software import news
from gest.tui.runtime import App, Screen, ansi_markup


def _line(text: str) -> urwid.Widget:
    return urwid.SelectableIcon(text, 0)


class NewsScreen(Screen):
    def __init__(self, app: App) -> None:
        self._numbers: list[int] = []
        self._item_walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._item_walker)
        self._content_walker = urwid.SimpleFocusListWalker(
            [urwid.Text("Select an item and press Enter to read it.")]
        )
        self._content = urwid.ListBox(self._content_walker)
        self._pile = urwid.Pile([
            ("weight", 2, urwid.LineBox(self._list, title="Portage news")),
            ("weight", 1, urwid.LineBox(self._content, title="Content")),
        ])
        super().__init__(
            app, self._pile, title="Portage News",
            footer_keys=[("Enter", "Read"), ("Tab", "Content"), ("Esc", "Back")],
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        items = await self.app.run_blocking(news.list_news)
        self._numbers = [it.number for it in items]
        rows = [
            urwid.AttrMap(
                _line(f"{'●' if it.unread else ' '} [{it.number}] {it.date}  {it.title}"),
                None, focus_map="focus",
            )
            for it in items
        ] or [urwid.Text(" (no news items)")]
        self._item_walker[:] = rows
        self.app.refresh()

    async def _read(self, number: int) -> None:
        body = await self.app.run_blocking(news.read_news, number)
        lines = [ansi_markup(x) for x in body.splitlines()] or ["(empty)"]
        self._content_walker[:] = [_line(line) for line in lines]
        self._content_walker.set_focus(0)
        self.app.refresh()

    def handle_key(self, key):
        if key == "esc":
            if self._pile.focus_position == 1:
                self._pile.focus_position = 0
            else:
                self.app.pop()
            return None
        if key == "tab":
            self._pile.focus_position = 0 if self._pile.focus_position == 1 else 1
            return None
        if key == "enter" and self._pile.focus_position == 0 and self._numbers:
            self.app.run_async(self._read(self._numbers[self._item_walker.focus]))
            return None
        return key
