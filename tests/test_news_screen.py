"""Headless test of the news viewer: list and read an item."""

from textual.widgets import DataTable

from gest.core.software.news import NewsItem
from gest.tui.app import GestApp
from gest.tui.screens.news import NewsScreen


async def test_news_list_and_read(monkeypatch):
    items = [
        NewsItem(1, "N", "2018-08-07", "OpenSSH LDAP migration"),
        NewsItem(2, "", "2019-05-23", "ACCEPT_LICENSE default"),
    ]
    monkeypatch.setattr("gest.core.software.news.list_news", lambda *a, **k: items)
    seen = {}

    def fake_read(number, *a, **k):
        seen["number"] = number
        return "body of the news item"

    monkeypatch.setattr("gest.core.software.news.read_news", fake_read)

    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(NewsScreen())
        await pilot.pause()
        await app.workers.wait_for_complete()  # list
        await pilot.pause()
        table = app.screen.query_one("#news", DataTable)
        assert table.row_count == 2
        table.focus()
        await pilot.pause()
        await pilot.press("enter")  # read first item
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert seen["number"] == 1
