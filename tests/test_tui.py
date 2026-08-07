"""Headless TUI tests driven by Textual's pilot."""

from textual.widgets import DataTable, Input, ListView

from gest.tui.app import GestApp, MainMenuScreen, SoftwareScreen


async def _open_software(app, pilot):
    """From a fresh app, open the Software module and wait for the load."""
    await pilot.pause()
    menu = app.screen.query_one("#module-list", ListView)
    menu.focus()
    await pilot.pause()
    await pilot.press("enter")  # select "Software Management"
    await pilot.pause()
    assert isinstance(app.screen, SoftwareScreen)
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_menu_opens_software_and_lists_installed():
    app = GestApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, MainMenuScreen)
        menu = app.screen.query_one("#module-list", ListView)
        assert len(menu.children) == 4  # one row per module
        await _open_software(app, pilot)
        table = app.screen.query_one("#results", DataTable)
        assert table.row_count > 0  # installed packages populated


async def test_software_search_narrows_results():
    app = GestApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await _open_software(app, pilot)
        installed_count = app.screen.query_one("#results", DataTable).row_count

        # The search box auto-focuses on mount; type an atom (with a slash)
        # directly and submit.
        for ch in "sys-apps/portage":
            await pilot.press(ch)
        assert app.screen.query_one("#search", Input).value == "sys-apps/portage"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()

        rows = app.screen.query_one("#results", DataTable).row_count
        assert 0 < rows < installed_count  # a search is a strict narrowing


async def test_slash_binding_focuses_search_and_preserves_slashes():
    """From the results table, "/" jumps to search; slashes then type literally."""
    app = GestApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await _open_software(app, pilot)
        # move focus away from the search box onto the table
        app.screen.query_one("#results", DataTable).focus()
        await pilot.pause()
        assert not isinstance(app.focused, Input)

        await pilot.press("/")  # quick-search binding
        await pilot.pause()
        assert isinstance(app.focused, Input)
        for ch in "x11-libs/gtk+":
            await pilot.press(ch)
        # the "/" mid-atom must be a literal character, not a re-trigger
        assert app.screen.query_one("#search", Input).value == "x11-libs/gtk+"


async def test_escape_returns_to_menu():
    app = GestApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await _open_software(app, pilot)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, MainMenuScreen)


async def test_menu_is_keyboard_navigable_without_focus_call():
    """The menu must be arrow+Enter drivable the instant it appears."""
    app = GestApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, MainMenuScreen)
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, SoftwareScreen)


async def test_down_arrow_moves_from_search_into_results():
    app = GestApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await _open_software(app, pilot)
        assert isinstance(app.focused, Input)  # search auto-focuses
        await pilot.press("down")
        await pilot.pause()
        assert isinstance(app.focused, DataTable)  # dropped into the list
