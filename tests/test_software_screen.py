"""Headless tests for the YaST-style Software Management screen."""

from textual.widgets import Checkbox, DataTable, Input, OptionList, Static

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
        # installed packages marked for install show "u" (update); "+" for new
        assert table.get_row_at(0)[0] in ("+", "u")
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


async def test_r_marks_remove_and_accept_chains_to_depclean():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_software(app, pilot)
        table = app.screen.query_one("#results", DataTable)
        table.focus()
        await pilot.pause()
        await pilot.press("r")  # mark row 0 for removal
        await pilot.pause()
        assert table.get_row_at(0)[0] == "-"
        assert app.screen._selection.remove_atoms()
        # only removes -> Accept goes straight to a depclean-multi apply
        app.screen.action_accept()
        await pilot.pause()
        assert isinstance(app.screen, InstallScreen)
        assert app.screen.mode == "depclean-multi"


async def test_accept_installs_then_chains_removes():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_software(app, pilot)
        table = app.screen.query_one("#results", DataTable)
        table.focus()
        await pilot.pause()
        await pilot.press("space")  # install-mark row 0
        await pilot.press("down")
        await pilot.press("r")      # remove-mark row 1
        await pilot.pause()
        app.screen.action_accept()
        await pilot.pause()
        assert app.screen.mode == "multi"          # phase 1: installs
        app.screen.dismiss()                       # simulate finishing phase 1
        await pilot.pause()
        assert isinstance(app.screen, InstallScreen)
        assert app.screen.mode == "depclean-multi"  # phase 2: removals


async def test_summary_checkbox_drives_search_fields(monkeypatch):
    captured = {}
    import gest.core.software.reader as reader_mod
    orig = reader_mod.search

    def fake(term, *, fields=("name",), limit=200):
        captured["fields"] = fields
        return orig("sys-apps/portage", fields=("name",))

    monkeypatch.setattr(reader_mod, "search", fake)
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_software(app, pilot)
        app.screen.query_one("#in-summary", Checkbox).value = True
        await pilot.pause()
        search = app.screen.query_one("#search", Input)
        search.focus()
        search.value = "vim"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["fields"] == ("name", "summary")
