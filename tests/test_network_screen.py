"""Headless test for the Network screen."""

from textual.widgets import DataTable, OptionList

from gest.tui.app import GestApp
from gest.tui.screens.network import InterfaceConfigScreen, NetworkScreen


async def test_network_screen_lists_interfaces():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.screen.query_one("#cc-categories", OptionList).focus()
        await pilot.pause()
        for _ in range(4):
            await pilot.press("down")  # Network category (index 4)
        await pilot.press("enter")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, NetworkScreen)
        await app.workers.wait_for_complete()
        await pilot.pause()
        table = app.screen.query_one("#net-table", DataTable)
        assert table.row_count > 0  # at least loopback
        assert next(str(c.label) for c in table.columns.values()) == "Interface"


async def _open_network(app, pilot):
    await pilot.pause()
    app.screen.query_one("#cc-categories", OptionList).focus()
    await pilot.pause()
    for _ in range(4):
        await pilot.press("down")  # Network category
    await pilot.press("enter")
    await pilot.press("enter")
    await pilot.pause()
    assert isinstance(app.screen, NetworkScreen)
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_configure_opens_modal_for_nonloopback():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_network(app, pilot)
        table = app.screen.query_one("#net-table", DataTable)
        table.focus()
        # find a non-loopback row
        for row in range(table.row_count):
            if str(table.get_row_at(row)[0]) != "lo":
                table.move_cursor(row=row)
                break
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, InterfaceConfigScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, NetworkScreen)
