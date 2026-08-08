"""Headless tests for the Users & Groups screen."""

from textual.widgets import DataTable, OptionList

from gest.tui.app import GestApp
from gest.tui.screens.users import (
    MemberFormScreen,
    PasswordFormScreen,
    UserFormScreen,
    UsersScreen,
)


async def _open_users(app, pilot):
    await pilot.pause()
    app.screen.query_one("#cc-categories", OptionList).focus()
    await pilot.pause()
    await pilot.press("down")   # System
    await pilot.press("down")   # Services
    await pilot.press("down")   # Security and Users
    await pilot.press("enter")  # module list
    await pilot.press("enter")  # Users & Groups
    await pilot.pause()
    assert isinstance(app.screen, UsersScreen)
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_users_list_and_group_toggle():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_users(app, pilot)
        table = app.screen.query_one("#users-table", DataTable)
        assert table.row_count > 0
        assert next(str(c.label) for c in table.columns.values()) == "Login"
        await pilot.press("g")  # toggle to groups
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert next(str(c.label) for c in table.columns.values()) == "Group"


async def test_add_opens_user_form_and_cancels():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_users(app, pilot)
        app.screen.query_one("#users-table", DataTable).focus()
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert isinstance(app.screen, UserFormScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, UsersScreen)


async def test_password_modal_opens():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_users(app, pilot)
        app.screen.query_one("#users-table", DataTable).focus()
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, PasswordFormScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, UsersScreen)


async def test_member_modal_opens_in_groups_view():
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_users(app, pilot)
        await pilot.press("g")  # switch to groups
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        app.screen.query_one("#users-table", DataTable).focus()
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        assert isinstance(app.screen, MemberFormScreen)
