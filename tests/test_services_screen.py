"""Headless test of the services screen: list, start, toggle-enable."""

from textual.widgets import DataTable

from gest.core.services.model import Service
from gest.tui.app import GestApp
from gest.tui.screens.services import ServicesScreen


class _FakeServicesBackend:
    calls: list = []

    async def connect(self):
        return self

    async def control(self, name, action):
        type(self).calls.append(("control", name, action))
        return [True, "ok"]

    async def set_enabled(self, name, enabled, runlevel="default"):
        type(self).calls.append(("enable", name, enabled))
        return [True, "ok"]

    async def close(self):
        pass


async def test_services_start_and_toggle_enable(monkeypatch):
    _FakeServicesBackend.calls = []
    rows = [Service("dbus", "started", ["default"]), Service("sshd", "stopped", [])]
    monkeypatch.setattr("gest.core.services.reader.list_services", lambda *a, **k: rows)
    monkeypatch.setattr("gest.tui.screens.services.ServicesBackend", _FakeServicesBackend)

    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(ServicesScreen())
        await pilot.pause()
        await app.workers.wait_for_complete()  # load
        await pilot.pause()
        table = app.screen.query_one("#services", DataTable)
        assert table.row_count == 2
        table.focus()
        await pilot.pause()

        await pilot.press("s")  # start the cursor row (dbus)
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert ("control", "dbus", "start") in _FakeServicesBackend.calls

        # move to sshd (disabled) and toggle-enable -> enable True
        await pilot.press("down")
        await pilot.pause()
        await pilot.press("e")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert ("enable", "sshd", True) in _FakeServicesBackend.calls
