"""Portage news viewer: list items and read their content (read-only)."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, RichLog, Static

from gest.core.software import news
from gest.core.software.backend_client import SoftwareBackend


class NewsScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("r", "mark_read", "Mark read"),
        Binding("a", "mark_all_read", "Mark all read"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._numbers: list[int] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Portage news — Enter read · r read · a all · Esc back", id="use-title")
        table = DataTable(id="news", cursor_type="row", zebra_stripes=True)
        table.add_columns("#", "", "Date", "Title")
        yield table
        yield RichLog(id="news-body", highlight=False, markup=False, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Portage News"
        self.query_one("#news", DataTable).focus()
        self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        items = news.list_news()
        self.app.call_from_thread(self._populate, items)

    def _populate(self, items: list[news.NewsItem]) -> None:
        table = self.query_one("#news", DataTable)
        table.clear()
        self._numbers = []
        for item in items:
            self._numbers.append(item.number)
            table.add_row(
                str(item.number),
                "●" if item.unread else " ",
                item.date,
                item.title,
                key=str(item.number),
            )
        if not items:
            self.query_one("#news-body", RichLog).write("No news items.")

    def _current_number(self) -> int | None:
        table = self.query_one("#news", DataTable)
        if not self._numbers:
            return None
        return self._numbers[table.cursor_row]

    def action_mark_read(self) -> None:
        number = self._current_number()
        if number is not None:
            self._mark(str(number))

    def action_mark_all_read(self) -> None:
        if self._numbers:
            self._mark("all")

    @work(exclusive=True)
    async def _mark(self, selector: str) -> None:
        backend = SoftwareBackend()
        try:
            await backend.connect()
            ok = await backend.mark_news_read(selector)
        except Exception as exc:
            self.app.notify(f"mark read: {exc}", severity="error")
            await backend.close()
            return
        await backend.close()
        target = "all items" if selector == "all" else f"item {selector}"
        self.app.notify(
            f"marked {target} read" if ok else f"could not mark {target} read",
            severity="information" if ok else "error",
        )
        self.load()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        number = int(event.data_table.get_row(event.row_key)[0])
        self.read_item(number)

    @work(thread=True, exclusive=True)
    def read_item(self, number: int) -> None:
        body = news.read_news(number)
        self.app.call_from_thread(self._show, body)

    def _show(self, body: str) -> None:
        log = self.query_one("#news-body", RichLog)
        log.clear()
        for line in body.splitlines():
            log.write(line)
