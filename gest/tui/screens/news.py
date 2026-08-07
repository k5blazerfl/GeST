"""Portage news viewer: list items and read their content (read-only)."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, RichLog, Static

from gest.core.software import news


class NewsScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._numbers: list[int] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Portage news — Enter to read", id="use-title")
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
