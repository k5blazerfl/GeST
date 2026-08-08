"""Headless tests for the YaST-style Software Management screen."""

from textual.widgets import DataTable, OptionList, Static

from gest.tui.app import GestApp, SoftwareScreen
from gest.tui.screens.install import InstallScreen
from gest.tui.screens.news import NewsScreen
from gest.tui.widgets.menu_bar import MenuBar, _MenuTitle


async def _open_software(app, pilot):
    await pilot.pause()
    app.screen.query_one("#cc-categories", OptionList).focus()
    await pilot.pause()
    await pilot.press("enter")  # category Software -> module list
    await pilot.press("enter")  # Software Management -> launch
    await pilot.pause()
    assert isinstance(app.screen, SoftwareScreen)
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_detail_pane_populates_on_highlight():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_software(app, pilot)
        table = app.screen.query_one("#results", DataTable)
        table.focus()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        detail = str(app.screen.query_one("#sw-detail", Static).render())
        assert "Version:" in detail and "Installed:" in detail


async def test_menubar_opens_and_closes_dropdown():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_software(app, pilot)
        app.screen.query_one("#menu-view", _MenuTitle).focus()
        await pilot.pause()
        await pilot.press("enter")  # open the View menu
        await pilot.pause()
        assert app.screen.query("#menu-dropdown")
        await pilot.press("escape")
        await pilot.pause()
        assert not app.screen.query("#menu-dropdown")


async def test_menu_selected_routes_to_news():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_software(app, pilot)
        app.screen.query_one(MenuBar).post_message(MenuBar.Selected("extras", "news"))
        await pilot.pause()
        assert isinstance(app.screen, NewsScreen)


async def test_menu_view_world_filters_count():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_software(app, pilot)
        app.screen.query_one(MenuBar).post_message(MenuBar.Selected("view", "world"))
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        count = str(app.screen.query_one("#sw-count", Static).render())
        assert "@world" in count


async def test_space_marks_rows_and_accept_opens_multi_apply():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_software(app, pilot)
        table = app.screen.query_one("#results", DataTable)
        table.focus()
        await pilot.pause()
        await pilot.press("space")   # mark row 0
        await pilot.press("down")
        await pilot.press("space")   # mark row 1
        await pilot.pause()
        assert len(app.screen._selection) == 2
        assert table.get_row_at(0)[0] == "+"  # status cell shows the mark
        count = str(app.screen.query_one("#sw-count", Static).render())
        assert "to install" in count
        app.screen.action_accept()
        await pilot.pause()
        assert isinstance(app.screen, InstallScreen)
        assert app.screen.mode == "multi"
        assert len(app.screen.atoms) == 2


async def test_clear_marks_resets_status():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_software(app, pilot)
        table = app.screen.query_one("#results", DataTable)
        table.focus()
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        assert not app.screen._selection.is_empty
        await pilot.press("c")
        await pilot.pause()
        assert app.screen._selection.is_empty
        assert table.get_row_at(0)[0] == "i"
