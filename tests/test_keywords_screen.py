"""Headless test of the keyword/mask editor: cycle, apply, confirm, write."""

from textual.widgets import DataTable

from gest.core.software import pkgconfig as pc
from gest.tui.app import GestApp
from gest.tui.screens.keywords import KeywordsScreen, _ConfirmScreen


class _FakeBackend:
    calls: list = []

    async def connect(self):
        return self

    async def set_package_config(self, kind, atom, line):
        type(self).calls.append((kind, atom, line))
        return True

    async def close(self):
        pass


async def test_keyword_cycle_apply_writes(monkeypatch, tmp_path):
    _FakeBackend.calls = []
    monkeypatch.setattr(pc, "gest_path", lambda kind: str(tmp_path / kind))
    monkeypatch.setattr("gest.tui.screens.keywords.SoftwareBackend", _FakeBackend)

    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(KeywordsScreen("app-misc/hello"))
        await pilot.pause()
        await app.workers.wait_for_complete()  # load_state
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, KeywordsScreen)
        screen.query_one("#settings", DataTable).focus()
        await pilot.pause()

        await pilot.press("space")  # keyword: default -> ~arch
        await pilot.pause()
        assert screen._kw == pc.KW_TESTING

        await pilot.press("a")
        await pilot.pause()
        assert isinstance(app.screen, _ConfirmScreen)
        await pilot.press("y")
        await app.workers.wait_for_complete()
        await pilot.pause()

        assert _FakeBackend.calls, "set_package_config not called"
        akw = [c for c in _FakeBackend.calls if c[0] == "accept_keywords"]
        assert akw and akw[0][1] == "app-misc/hello" and "~" in akw[0][2]
