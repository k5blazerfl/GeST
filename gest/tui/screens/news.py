"""Portage news viewer (urwid): list items, read content, mark read.

Two panes — the item list (● = unread) with an unread count, and the read
item's content (styled header block + word-wrapped body + highlighted footnote
links). Enter reads an item and marks it read; r marks the focused item read;
a marks all read. Reads are persisted through the backend (eselect news read,
polkit-gated); the ● clears optimistically for immediate feedback.
"""

from __future__ import annotations

import contextlib
import re

import urwid

from gest.core.software import news
from gest.core.software.backend_client import SoftwareBackend
from gest.core.software.news import NewsItem
from gest.tui.runtime import App, NavPile, Screen, ansi_markup, boxed

_LINK = re.compile(r"^\s*\[\d+\]\s")   # a "[1] https://…" footnote line


class NewsScreen(Screen):
    def __init__(self, app: App) -> None:
        self._items: list[NewsItem] = []
        self._item_walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._item_walker)
        self._content_walker = urwid.SimpleFocusListWalker(
            [urwid.Text("Select an item and press Enter to read it.")])
        self._content = urwid.ListBox(self._content_walker)
        self._count = urwid.Text("")
        self._pile = NavPile([
            ("weight", 2, boxed(self._list, title="Portage news")),
            ("pack", self._count),
            ("weight", 1, boxed(self._content, title="Content")),
        ])
        super().__init__(
            app, self._pile, title="Portage News",
            footer_keys=[("Enter", "Read"), ("Tab", "Content"), ("Esc", "Back")],
            help_text=(
                "Gentoo news items relevant to this system.\n\n"
                "●   marks an unread item.\n"
                "Enter   read the item (and mark it read)\n"
                "r       mark the highlighted item read\n"
                "a       mark all items read\n"
                "Tab     switch to the content pane   ↑/↓ scrolls it\n"
                "Esc     back to the list, then out"))
        self.configure_pane_cycle(self._pile, [0, 2])   # Tab toggles list/content
        self._refresh_footer()
        app.run_async(self._load())

    def _footer_context(self):
        if self._pile.focus_position == 0:              # news list
            return [("Enter", "Read"), ("r", "Mark read"), ("a", "All read"),
                    ("Tab", "Content"), ("Esc", "Back")]
        return [("↑↓", "Scroll"), ("Tab", "List"), ("Esc", "List")]  # content

    # -- loading / list -----------------------------------------------------

    async def _load(self) -> None:
        self._items = await self.app.run_blocking(news.list_news)
        self._render_list()
        # Land on the first unread item so the reader opens where it matters.
        first_unread = next((i for i, it in enumerate(self._items) if it.unread), 0)
        if self._items:
            self._item_walker.set_focus(first_unread)
        self.app.refresh()

    def _render_list(self) -> None:
        focus = self._item_walker.focus or 0
        rows = [
            urwid.AttrMap(
                urwid.SelectableIcon(
                    f"{'●' if it.unread else ' '} [{it.number}] {it.date}  "
                    f"{it.title}", 0),
                "field" if it.unread else None, focus_map="focus")
            for it in self._items
        ] or [urwid.Text(" (no news items)")]
        self._item_walker[:] = rows
        if self._items:
            self._item_walker.set_focus(min(focus, len(self._items) - 1))
        self._refresh_count()
        self.app.refresh()

    def _refresh_count(self) -> None:
        n = len(self._items)
        unread = sum(1 for it in self._items if it.unread)
        if not n:
            self._count.set_text(("dim", " No news items"))
        elif unread:
            self._count.set_text([("field", f" {unread} unread"),
                                  ("dim", f"  ·  {n} item{'s' if n != 1 else ''}"
                                          "   ·   a  mark all read")])
        else:
            self._count.set_text(("dim", f" {n} item{'s' if n != 1 else ''}"
                                         " · all read"))

    # -- reading ------------------------------------------------------------

    def _current(self) -> NewsItem | None:
        i = self._item_walker.focus
        return self._items[i] if self._items and 0 <= i < len(self._items) else None

    async def _read(self, item: NewsItem) -> None:
        raw = await self.app.run_blocking(news.read_news, item.number)
        parsed = news.parse_content(raw)
        # All rows are selectable icons so the content pane scrolls from the
        # styled header down through the body (the header shows first).
        rows: list[urwid.Widget] = []
        for label, value in parsed.headers:
            markup = ([("box_title", f" {value}")] if label.lower() == "title"
                      else [("hint", f" {label}: "), value])
            rows.append(urwid.SelectableIcon(markup, 0))
        if parsed.headers:
            rows.append(urwid.Divider("─"))
        for line in parsed.body:
            markup = [("field", line)] if _LINK.match(line) else ansi_markup(line)
            rows.append(urwid.SelectableIcon(markup or " ", 0))
        self._content_walker[:] = rows or [urwid.Text("(empty)")]
        self._content_walker.set_focus(0)               # show the header first
        self.app.refresh()

    # -- marking read -------------------------------------------------------

    async def _mark(self, selector: str, *, silent: bool = False) -> None:
        # Optimistic: clear the ● now for instant feedback, then persist.
        for it in self._items:
            if selector == "all" or str(it.number) == selector:
                it.status = "-"
        self._render_list()
        backend = SoftwareBackend()
        try:
            await backend.connect()
            ok = await backend.mark_news_read(selector)
        except Exception as exc:
            with contextlib.suppress(Exception):
                await backend.close()
            if not silent:
                self.app.notify(f"Couldn't persist read: {exc}", error=True)
            return
        await backend.close()
        if not ok and not silent:
            self.app.notify("Couldn't mark read.", error=True)

    def handle_key(self, key):
        if key == "esc":
            if self._pile.focus_position != 0:
                self._pile.focus_position = 0    # content → list
            else:
                self.app.pop()
            return None
        if self._pile.focus_position == 0 and self._items:
            item = self._current()
            if key == "enter" and item is not None:
                self.app.run_async(self._read(item))
                self.app.run_async(self._mark(str(item.number), silent=True))
                return None
            if key == "r" and item is not None:
                self.app.run_async(self._mark(str(item.number)))
                return None
            if key == "a":
                self.app.run_async(self._mark("all"))
                return None
        return key
