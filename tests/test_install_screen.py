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
        app.push_screen(InstallScreen("app-misc/hello", mode="rebuild"))
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


async def test_world_mode_previews_and_calls_update_world(monkeypatch):
    canned = PreviewResult("@world", 0, "Total: 12 packages (12 upgrades)")

    class _WorldBackend(_FakeBackend):
        updated: list = []

        async def update_world(self, on_progress=None, on_finished=None):
            type(self).updated.append(True)
            if on_progress:
                on_progress(">>> updating @world")
            if on_finished:
                on_finished(0)
            return True

    _WorldBackend.updated = []
    monkeypatch.setattr(
        "gest.core.software.preview.preview_world", lambda **k: canned
    )
    monkeypatch.setattr("gest.tui.screens.install.SoftwareBackend", _WorldBackend)

    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(InstallScreen("@world", mode="world"))
        await pilot.pause()
        await app.workers.wait_for_complete()  # preview_world
        await pilot.pause()
        btn = app.screen.query_one("#install", Button)
        assert btn.label.plain == "System update"
        assert btn.disabled is False
        await pilot.press("i")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert _WorldBackend.updated == [True]


async def test_depclean_mode_previews_and_calls_depclean(monkeypatch):
    canned = PreviewResult("cat/pkg", 0, "Number to remove: 1")
    seen = {}

    def fake_preview(atom="", **k):
        seen["atom"] = atom
        return canned

    class _DepcleanBackend(_FakeBackend):
        removed: list = []

        async def depclean(self, atom="", on_progress=None, on_finished=None):
            type(self).removed.append(atom)
            if on_progress:
                on_progress(">>> Unmerging")
            if on_finished:
                on_finished(0)
            return True

    _DepcleanBackend.removed = []
    monkeypatch.setattr("gest.core.software.preview.preview_depclean", fake_preview)
    monkeypatch.setattr("gest.tui.screens.install.SoftwareBackend", _DepcleanBackend)

    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(InstallScreen("cat/pkg", mode="depclean"))
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert seen["atom"] == "cat/pkg"
        assert app.screen.query_one("#install", Button).label.plain == "Remove"
        await pilot.press("i")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert _DepcleanBackend.removed == ["cat/pkg"]


async def test_sync_mode_calls_sync(monkeypatch):
    class _SyncBackend(_FakeBackend):
        synced: list = []

        async def sync(self, on_progress=None, on_finished=None):
            type(self).synced.append(True)
            if on_progress:
                on_progress(">>> syncing")
            if on_finished:
                on_finished(0)
            return True

    _SyncBackend.synced = []
    monkeypatch.setattr("gest.tui.screens.install.SoftwareBackend", _SyncBackend)

    app = GestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(InstallScreen("", mode="sync"))
        await pilot.pause()
        await app.workers.wait_for_complete()  # informational preview
        await pilot.pause()
        btn = app.screen.query_one("#install", Button)
        assert btn.label.plain == "Sync"
        assert btn.disabled is False
        await pilot.press("i")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert _SyncBackend.synced == [True]
