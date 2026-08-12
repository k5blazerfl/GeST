"""Portage news viewer (urwid): list items, read content, mark read.

The item list (● = unread) with an unread count, a read-item preview pane, and
Tab-able [Exit] / [Read] buttons. Enter previews the focused item (and marks it
read); a second Enter on the same item opens it full-screen. u filters to
unread only; n/p jump between unread; r / a mark the focused / all items read.
Reads are persisted through the backend (eselect news read, polkit-gated); the
● clears optimistically for immediate feedback.
"""

from __future__ import annotations

import contextlib
import re

import urwid

from gest.core.software import news
from gest.core.software.backend_client import SoftwareBackend
from gest.core.software.news import NewsItem
from gest.tui.runtime import App, NavPile, Screen, ansi_markup, boxed, focusable_actions

_LINK = re.compile(r"^\s*\[\d+\]\s")   # a "[1] https://…" footnote line


def _content_rows(parsed: news.NewsContent) -> list[urwid.Widget]:
    """Selectable rows for a read item: styled header, divider, then body.

    All rows are selectable icons so the pane scrolls from the header down
    through the body; the Title is blue, other headers are ``label: value``,
    and ``[n] http…`` footnote links are highlighted.
    """
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
    return rows or [urwid.Text("(empty)")]


class NewsScreen(Screen):
    def __init__(self, app: App) -> None:
        self._items: list[NewsItem] = []        # every item
        self._visible: list[NewsItem] = []      # what the list currently shows
        self._unread_only = False
        self._previewed: NewsItem | None = None  # item shown in the preview pane
        self._item_walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._item_walker)
        self._content_walker = urwid.SimpleFocusListWalker(
            [urwid.Text("Select an item and press Enter to read it "
                        "(Enter again for full screen).")])
        self._content = urwid.ListBox(self._content_walker)
        self._count = urwid.Text("")
        self._actions = focusable_actions([
            ("Exit", app.pop), ("Read", self._activate_read)])
        self._pile = NavPile([
            ("weight", 2, boxed(self._list, title="Portage news")),
            ("pack", self._count),
            ("weight", 1, boxed(self._content, title="Content")),
            ("pack", self._actions),
        ])
        super().__init__(
            app, self._pile, title="Portage News",
            footer_keys=[("Enter", "Read"), ("Esc", "Back")],
            help_text=(
                "Gentoo news items relevant to this system.\n\n"
                "●   marks an unread item.\n"
                "Enter   read the item in the preview pane (and mark it read);\n"
                "        Enter again on the same item opens it full-screen\n"
                "u       toggle showing only unread items\n"
                "n / p   jump to the next / previous unread item\n"
                "r       mark the highlighted item read\n"
                "a       mark all items read\n"
                "Tab     move to the Exit / Read buttons\n"
                "Esc     back to the menu"))
        self.configure_pane_cycle(self._pile, [0], action_row=self._actions)
        self._refresh_footer()
        app.run_async(self._load())

    def _footer_context(self):
        if self._on_action_row():
            return [("Enter", "Activate"), ("Tab", "Next"), ("Esc", "Back")]
        return [("Enter", "Read"),
                ("u", "Show all" if self._unread_only else "Unread only"),
                ("n/p", "Jump unread"), ("r", "Mark read"), ("a", "All read"),
                ("Tab", "Buttons"), ("Esc", "Back")]

    # -- loading / list -----------------------------------------------------

    async def _load(self) -> None:
        self._items = await self.app.run_blocking(news.list_news)
        self._render_list()
        # Land on the first unread item so the reader opens where it matters.
        first = next((i for i, it in enumerate(self._visible) if it.unread), 0)
        if self._visible:
            self._item_walker.set_focus(first)
        self.app.refresh()

    def _render_list(self) -> None:
        focus = self._item_walker.focus or 0
        self._visible = ([it for it in self._items if it.unread]
                         if self._unread_only else self._items)
        if not self._visible:
            msg = " No unread news." if self._unread_only else " (no news items)"
            self._item_walker[:] = [urwid.Text(("dim", msg))]
        else:
            self._item_walker[:] = [
                urwid.AttrMap(
                    urwid.SelectableIcon(
                        f"{'●' if it.unread else ' '} [{it.number}] {it.date}  "
                        f"{it.title}", 0),
                    "field" if it.unread else None, focus_map="focus")
                for it in self._visible]
            self._item_walker.set_focus(min(focus, len(self._visible) - 1))
        self._refresh_count()
        self.app.refresh()

    def _refresh_count(self) -> None:
        n = len(self._items)
        unread = sum(1 for it in self._items if it.unread)
        if not n:
            self._count.set_text(("dim", " No news items"))
        elif self._unread_only:
            self._count.set_text([("field", f" Unread only — {unread}"),
                                  ("dim", f"   ·   {n} total   ·   u  show all")])
        elif unread:
            self._count.set_text([("field", f" {unread} unread"),
                                  ("dim", f"  ·  {n} item{'s' if n != 1 else ''}"
                                          "   ·   u  unread only   ·   a  mark all")])
        else:
            self._count.set_text(("dim", f" {n} item{'s' if n != 1 else ''}"
                                         " · all read"))

    # -- reading ------------------------------------------------------------

    def _current(self) -> NewsItem | None:
        i = self._item_walker.focus
        return (self._visible[i]
                if self._visible and 0 <= i < len(self._visible) else None)

    def _toggle_filter(self) -> None:
        self._unread_only = not self._unread_only
        self._render_list()
        if self._visible:
            self._item_walker.set_focus(0)
        self._refresh_footer()

    def _jump_unread(self, delta: int) -> None:
        """Move focus to the next (delta=1) / previous (delta=-1) unread item."""
        if not self._visible:
            return
        n = len(self._visible)
        start = self._item_walker.focus or 0
        for step in range(1, n + 1):
            i = (start + delta * step) % n           # wrap around
            if self._visible[i].unread:
                self._item_walker.set_focus(i)
                return

    def _activate_read(self) -> None:
        """Enter / the Read button: first press previews the item (and marks it
        read); a second press on the same item opens it full-screen."""
        item = self._current()
        if item is None:
            return
        if item is self._previewed:
            self.app.run_async(self._read_fullscreen(item))
        else:
            self._previewed = item
            self.app.run_async(self._read(item))
            self.app.run_async(self._mark(str(item.number), silent=True))

    async def _read(self, item: NewsItem) -> None:
        raw = await self.app.run_blocking(news.read_news, item.number)
        self._content_walker[:] = _content_rows(news.parse_content(raw))
        self._content_walker.set_focus(0)               # show the header first
        self.app.refresh()

    async def _read_fullscreen(self, item: NewsItem) -> None:
        raw = await self.app.run_blocking(news.read_news, item.number)
        # The reader's [Back] / [Mark Unread] buttons decide the read state on
        # exit — so don't mark here.
        self.app.push(NewsReaderScreen(self.app, item, news.parse_content(raw),
                                       on_close=self._reader_closed))

    def _reader_closed(self, item: NewsItem, read: bool) -> None:
        selector = str(item.number)
        if read:
            self.app.run_async(self._mark(selector, silent=True))
        else:
            self.app.run_async(self._mark_unread(selector, silent=True))

    # -- marking read / unread ----------------------------------------------

    async def _set_read(self, selector: str, read: bool, silent: bool) -> None:
        # Optimistic: flip the ● now for instant feedback, then persist.
        for it in self._items:
            if selector == "all" or str(it.number) == selector:
                it.status = "-" if read else "N"
        self._render_list()
        backend = SoftwareBackend()
        verb = "read" if read else "unread"
        try:
            await backend.connect()
            ok = await (backend.mark_news_read(selector) if read
                        else backend.mark_news_unread(selector))
        except Exception as exc:
            with contextlib.suppress(Exception):
                await backend.close()
            if not silent:
                self.app.notify(f"Couldn't mark {verb}: {exc}", error=True)
            return
        await backend.close()
        if not ok and not silent:
            self.app.notify(f"Couldn't mark {verb}.", error=True)

    async def _mark(self, selector: str, *, silent: bool = False) -> None:
        await self._set_read(selector, True, silent)

    async def _mark_unread(self, selector: str, *, silent: bool = False) -> None:
        await self._set_read(selector, False, silent)

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if self._on_action_row():
            return key                           # nav owns Tab / Enter on buttons
        if key == "enter":
            self._activate_read()                # preview, or full-screen on repeat
            return None
        item = self._current()
        if key in ("f", "F") and item is not None:   # direct full-screen shortcut
            self.app.run_async(self._read_fullscreen(item))
            return None
        if not self._items:
            return key
        if key in ("u", "U"):
            self._toggle_filter()
            return None
        if key == "n":
            self._jump_unread(1)
            return None
        if key == "p":
            self._jump_unread(-1)
            return None
        if key == "r" and item is not None:
            self.app.run_async(self._mark(str(item.number)))
            return None
        if key == "a":
            self.app.run_async(self._mark("all"))
            return None
        return key


class NewsReaderScreen(Screen):
    """Full-screen reader for a single news item — better for long items.

    Shows the styled item (header + word-wrapped body + links) across the whole
    pane; ↑/↓ scroll a line, ←/→ page back/forward, Tab reaches the buttons.
    [Back] returns to the list marking the item read; [Mark Unread] returns
    leaving it flagged unread. ``on_close(item, read)`` reports the choice.
    """

    # ← previous page, → next page — remapped onto the ListBox's paging.
    _PAGE = {"left": "page up", "right": "page down"}

    def __init__(self, app: App, item: NewsItem, parsed: news.NewsContent, *,
                 on_close) -> None:
        self._item = item
        self._on_close = on_close
        self._closed = False
        self._walker = urwid.SimpleFocusListWalker(_content_rows(parsed))
        content = boxed(urwid.ListBox(self._walker), title=item.title)
        self._actions = focusable_actions([
            ("Mark Unread", self._mark_unread), ("Back", self._back)])
        body = NavPile([("weight", 1, content), ("pack", self._actions)])
        super().__init__(
            app, body, title="Portage News",
            footer_keys=[("↑/↓", "Scroll"), ("←/→", "Page"),
                         ("Tab", "Buttons"), ("Esc", "Back")],
            help_text=("Reading a Portage news item full-screen.\n"
                       "↑/↓ scroll a line · ←/→ page · Tab to the buttons.\n"
                       "Back returns and marks it read; Mark Unread returns "
                       "leaving it unread.  Esc = Back."))
        self.configure_pane_cycle(body, [0], action_row=self._actions)
        self._refresh_footer()

    def _footer_context(self):
        if self._on_action_row():
            return [("Enter", "Activate"), ("Tab", "Next"), ("Esc", "Back")]
        return [("↑/↓", "Scroll"), ("←/→", "Page"),
                ("Tab", "Buttons"), ("Esc", "Back")]

    def keypress(self, size, key):
        # Page with ←/→ only while reading; on the buttons they move between them.
        if key in ("left", "right") and not self._on_action_row():
            key = self._PAGE[key]
        return super().keypress(size, key)

    def _close(self, *, read: bool) -> None:
        if self._closed:
            return
        self._closed = True
        self._on_close(self._item, read)
        self.app.pop()

    def _back(self) -> None:
        self._close(read=True)

    def _mark_unread(self) -> None:
        self._close(read=False)

    def handle_key(self, key):
        if key == "esc":
            self._close(read=True)          # Esc = Back → marks read
            return None
        return key
