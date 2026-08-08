"""Headless tests for the System settings screens."""

from textual.widgets import Input, OptionList

from gest.tui.app import GestApp
from gest.tui.screens.system import HostnameScreen, LocaleScreen, TimezoneScreen


async def _open_system_module(app, pilot, down_in_modules):
    await pilot.pause()
    app.screen.query_one("#cc-categories", OptionList).focus()
    await pilot.pause()
    await pilot.press("down")   # System category (index 1)
    await pilot.press("enter")  # focus its module list
    for _ in range(down_in_modules):
        await pilot.press("down")
    await pilot.press("enter")
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_hostname_screen_prefills_current():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_system_module(app, pilot, 0)
        assert isinstance(app.screen, HostnameScreen)
        assert app.screen.query_one("#hostname-input", Input).value  # non-empty


async def test_timezone_screen_lists_and_filters():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_system_module(app, pilot, 1)
        assert isinstance(app.screen, TimezoneScreen)
        ol = app.screen.query_one("#choice-list", OptionList)
        total = ol.option_count
        assert total > 100  # the full zoneinfo set
        f = app.screen.query_one("#choice-filter", Input)
        f.focus()
        f.value = "reykjavik"
        await pilot.pause()
        assert ol.option_count < total


async def test_locale_screen_opens():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_system_module(app, pilot, 2)
        assert isinstance(app.screen, LocaleScreen)
        assert app.screen.query_one("#choice-list", OptionList).option_count >= 1
