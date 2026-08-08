"""Headless TUI tests driven by Textual's pilot."""

from textual.widgets import DataTable, Input, OptionList

from gest.tui.app import GestApp, MainMenuScreen, SoftwareScreen
from gest.tui.widgets.bracket_button import BracketButton


async def _open_software(app, pilot):
    """From a fresh app, open the Software module and wait for the load."""
    await pilot.pause()
    app.screen.query_one("#cc-categories", OptionList).focus()
    await pilot.pause()
    await pilot.press("enter")  # category Software -> focus its module list
    await pilot.press("enter")  # module "Software Management" -> launch
    await pilot.pause()
    assert isinstance(app.screen, SoftwareScreen)
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_menu_opens_software_and_lists_installed():
    app = GestApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, MainMenuScreen)
        cats = app.screen.query_one("#cc-categories", OptionList)
        assert cats.option_count == 4  # Software / Services / Users / Network
        mods = app.screen.query_one("#cc-modules", OptionList)
        assert mods.option_count == 5  # the Software category's modules
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
        cats = app.screen.query_one("#cc-categories", OptionList)
        assert app.focused is cats  # categories focused, arrows work immediately
        await pilot.press("down")   # Services
        await pilot.press("up")     # back to Software (index 0)
        await pilot.press("enter")  # -> module list
        await pilot.press("enter")  # Software Management -> launch
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


async def test_menu_arrow_navigates_all_items_and_notifies_unimplemented():
    app = GestApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        cats = app.screen.query_one("#cc-categories", OptionList)
        assert app.focused is cats  # categories focused, arrows work immediately
        await pilot.press("down")   # Services
        await pilot.press("down")   # Security and Users
        await pilot.press("enter")  # -> its module list (Users & Groups)
        await pilot.press("enter")  # launch an unimplemented module
        await pilot.pause()
        assert isinstance(app.screen, MainMenuScreen)  # unimplemented -> stays put


async def test_menu_system_update_opens_world_screen(monkeypatch):
    from gest.core.software.preview import PreviewResult
    from gest.tui.screens.install import InstallScreen

    monkeypatch.setattr(
        "gest.core.software.preview.preview_world",
        lambda **k: PreviewResult("@world", 0, "Total: 0 packages"),
    )
    app = GestApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.press("enter")  # category Software -> module list (idx 0)
        await pilot.press("down")   # module idx 1 = System Update
        await pilot.press("enter")  # launch
        await pilot.pause()
        assert isinstance(app.screen, InstallScreen)
        assert app.screen.mode == "world"


async def test_menu_cleanup_opens_system_depclean(monkeypatch):
    from gest.core.software.preview import PreviewResult
    from gest.tui.screens.install import InstallScreen

    monkeypatch.setattr(
        "gest.core.software.preview.preview_depclean",
        lambda atom="", **k: PreviewResult(atom or "@world", 0, "Number to remove: 0"),
    )
    app = GestApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.press("enter")  # category Software -> module list (idx 0)
        await pilot.press("down")   # 1 System Update
        await pilot.press("down")   # 2 Clean Up Packages
        await pilot.press("enter")  # launch
        await pilot.pause()
        assert isinstance(app.screen, InstallScreen)
        assert app.screen.mode == "depclean"
        assert app.screen.atom == ""  # system-wide


async def test_menu_run_button_launches_highlighted():
    """The [Run] bracket button opens the highlighted module (Software Mgmt)."""
    app = GestApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, MainMenuScreen)
        app.screen.query_one("#run", BracketButton).post_message(
            BracketButton.Pressed(app.screen.query_one("#run", BracketButton))
        )
        await pilot.pause()
        assert isinstance(app.screen, SoftwareScreen)
