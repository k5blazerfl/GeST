"""Headless test of the USE-flag editor: cycle a flag, apply, confirm, write."""

from textual.widgets import DataTable

from gest.core.software.useflags import DEFAULT, ON, FlagRow
from gest.tui.app import GestApp
from gest.tui.screens.useflags import ConfirmWriteScreen, UseFlagScreen


class _FakeBackend:
    calls: list = []

    async def connect(self):
        return self

    async def set_package_use(self, atom, line):
        type(self).calls.append((atom, line))
        return True

    async def close(self):
        pass


async def test_cycle_apply_confirm_writes(monkeypatch, tmp_path):
    _FakeBackend.calls = []
    rows = [
        FlagRow("jack", False, DEFAULT, "JACK audio"),
        FlagRow("pgo", True, DEFAULT, "profile-guided optimisation"),
    ]
    monkeypatch.setattr("gest.core.software.useflags.flags_for", lambda cp: rows)
    monkeypatch.setattr("gest.core.software.useflags.gest_file", lambda: str(tmp_path / "gest"))
    monkeypatch.setattr("gest.tui.screens.useflags.SoftwareBackend", _FakeBackend)

    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(UseFlagScreen("www-client/firefox"))
        await pilot.pause()
        await app.workers.wait_for_complete()  # load_flags
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, UseFlagScreen)
        table = screen.query_one("#flags", DataTable)
        assert table.row_count == 2
        table.focus()
        await pilot.pause()

        await pilot.press("space")  # cursor row 0 = jack: default -> on
        await pilot.pause()
        assert screen._states["jack"] == ON

        await pilot.press("a")  # apply -> confirm modal
        await pilot.pause()
        assert isinstance(app.screen, ConfirmWriteScreen)
        await pilot.press("y")  # confirm
        await app.workers.wait_for_complete()  # _write worker
        await pilot.pause()

        assert _FakeBackend.calls, "backend.set_package_use was not called"
        atom, line = _FakeBackend.calls[-1]
        assert atom == "www-client/firefox"
        assert "jack" in line
