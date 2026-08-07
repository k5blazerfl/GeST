"""Headless tests of the install screen: preview gate + streamed merge."""

from textual.widgets import Button, DataTable, ListView

from gest.core.software.preview import PreviewResult
from gest.tui.app import GestApp
from gest.tui.screens.install import InstallScreen


class _FakeBackend:
    """Stand-in for the D-Bus backend: streams two lines, exits 0."""

    async def connect(self):
        return self

    async def install(self, atom, on_progress=None, on_finished=None):
        if on_progress:
            on_progress(f">>> Emerging ({atom})")
            on_progress(">>> Installing")
        if on_finished:
            on_finished(0)
        return True

    async def close(self):
        pass


class _UnavailableBackend:
    async def connect(self):
        raise ConnectionError("org.gentoo.gest not provided by any process")

    async def close(self):
        pass


async def _open_install_screen(app, pilot):
    await pilot.pause()
    app.screen.query_one("#module-list", ListView).focus()
    await pilot.pause()
    await pilot.press("enter")  # open Software Management
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()
    table = app.screen.query_one("#results", DataTable)
    table.focus()
    await pilot.pause()
    await pilot.press("enter")  # select first package row
    await pilot.pause()
    assert isinstance(app.screen, InstallScreen)
    await app.workers.wait_for_complete()  # preview worker
    await pilot.pause()


async def test_resolvable_preview_enables_install_then_completes(monkeypatch):
    canned = PreviewResult(
        "x/y", 0,
        "Calculating dependencies ... done!\n"
        "Total: 1 package (1 new), Size of downloads: 0 KiB",
    )
    monkeypatch.setattr(
        "gest.core.software.preview.preview_install", lambda atom, **k: canned
    )
    monkeypatch.setattr("gest.tui.screens.install.SoftwareBackend", _FakeBackend)

    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_install_screen(app, pilot)
        install_btn = app.screen.query_one("#install", Button)
        assert install_btn.disabled is False  # preview resolved -> enabled

        await pilot.press("i")  # confirm install
        await app.workers.wait_for_complete()
        await pilot.pause()

        assert app.screen._done is True
        assert app.screen._installing is False
        assert app.screen.query_one("#cancel", Button).label.plain == "Back"


async def test_unresolvable_preview_keeps_install_disabled(monkeypatch):
    canned = PreviewResult("x/y", 1, '!!! There are no ebuilds to satisfy "x/y".')
    monkeypatch.setattr(
        "gest.core.software.preview.preview_install", lambda atom, **k: canned
    )
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_install_screen(app, pilot)
        assert app.screen.query_one("#install", Button).disabled is True
        assert app.screen._done is False


async def test_backend_unavailable_is_reported(monkeypatch):
    canned = PreviewResult(
        "x/y", 0, "Total: 1 package (1 new), Size of downloads: 0 KiB"
    )
    monkeypatch.setattr(
        "gest.core.software.preview.preview_install", lambda atom, **k: canned
    )
    monkeypatch.setattr(
        "gest.tui.screens.install.SoftwareBackend", _UnavailableBackend
    )
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_install_screen(app, pilot)
        await pilot.press("i")
        await app.workers.wait_for_complete()
        await pilot.pause()

        # graceful: not stuck "installing", and offers a way back
        assert app.screen._installing is False
        assert app.screen._done is False
        assert app.screen.query_one("#cancel", Button).label.plain == "Back"


async def test_install_button_autofocuses_when_plan_resolves(monkeypatch):
    canned = PreviewResult(
        "x/y", 0, "Total: 1 package (1 new), Size of downloads: 0 KiB"
    )
    monkeypatch.setattr(
        "gest.core.software.preview.preview_install", lambda atom, **k: canned
    )
    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await _open_install_screen(app, pilot)
        assert isinstance(app.focused, Button)
        assert app.focused.id == "install"  # Enter confirms — no mouse needed


async def test_rebuild_mode_previews_changed_use_and_calls_rebuild(monkeypatch):
    canned = PreviewResult(
        "x/y", 0, "Total: 1 package (1 reinstall), Size of downloads: 0 KiB"
    )
    seen = {}

    def fake_preview(atom, changed_use=False, **k):
        seen["changed_use"] = changed_use
        return canned

    class _RebuildBackend(_FakeBackend):
        rebuilt: list = []

        async def rebuild(self, atom, on_progress=None, on_finished=None):
            type(self).rebuilt.append(atom)
            if on_progress:
                on_progress(">>> rebuilding")
            if on_finished:
                on_finished(0)
            return True

    _RebuildBackend.rebuilt = []
    monkeypatch.setattr("gest.core.software.preview.preview_install", fake_preview)
    monkeypatch.setattr("gest.tui.screens.install.SoftwareBackend", _RebuildBackend)

    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(InstallScreen("app-misc/hello", rebuild=True))
        await pilot.pause()
        await app.workers.wait_for_complete()  # preview worker
        await pilot.pause()
        assert seen["changed_use"] is True
        btn = app.screen.query_one("#install", Button)
        assert btn.label.plain == "Rebuild"
        assert btn.disabled is False
        await pilot.press("i")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert _RebuildBackend.rebuilt == ["app-misc/hello"]
