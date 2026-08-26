"""Offscreen smoke for the Default Browser module — wiring, no real commands."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from gest.core.defaultapps import browser as browsers
from gest.qt.modules import defaultbrowser as mod


def _app():
    return QApplication.instance() or QApplication([])


def test_descriptor_is_registerable():
    assert mod.DESCRIPTOR.icon  # rail always has an icon to render
    assert mod.DESCRIPTOR.category == "Software"


def test_populates_and_reflects_no_default(monkeypatch):
    _app()
    # never touch the real system: no browser installed, no default set
    monkeypatch.setattr(mod, "_is_installed", lambda b: False)
    monkeypatch.setattr(mod, "_run", lambda argv: (True, ""))
    w = mod.factory()
    assert w._list.count() == len(browsers.BROWSERS)
    assert "none set" in w._current.text()
    # recommended browser is pre-selected → button offers to install it
    assert w._use.text() == "Install & set default"


class _Sig:
    def connect(self, *a):
        pass


class _FakeWorker:
    def __init__(self, atom):
        self.atom = atom
        self.output = _Sig()
        self.done = _Sig()

    def isRunning(self):
        return False

    def start(self):
        pass


def _select(w, browser_id):
    idx = next(i for i, br in enumerate(browsers.BROWSERS) if br.id == browser_id)
    w._list.setCurrentRow(idx)


def test_licensed_browser_accepts_eula_then_installs(monkeypatch):
    _app()
    monkeypatch.setattr(mod, "_is_installed", lambda b: False)
    monkeypatch.setattr(mod, "_run", lambda argv: (True, ""))
    monkeypatch.setattr(mod, "InstallWorker", _FakeWorker)
    accepted: list[tuple[str, tuple[str, ...]]] = []

    def fake_accept(atom, lics):
        accepted.append((atom, tuple(lics)))
        return (True, "")
    monkeypatch.setattr(mod, "set_atom_licenses", fake_accept)

    w = mod.factory()
    _select(w, "opera")
    w._on_use()
    # the EULA was accepted for the exact atom, then the install worker started
    assert accepted == [("www-client/opera", ("OPERA-2018",))]
    assert isinstance(w._worker, _FakeWorker) and w._worker.atom == "www-client/opera"


def test_license_rejection_aborts_the_install(monkeypatch):
    _app()
    monkeypatch.setattr(mod, "_is_installed", lambda b: False)
    monkeypatch.setattr(mod, "_run", lambda argv: (True, ""))
    monkeypatch.setattr(mod, "set_atom_licenses", lambda atom, lics: (False, "not authorized"))
    started = []

    def fake_worker(atom):
        started.append(atom)
    monkeypatch.setattr(mod, "InstallWorker", fake_worker)

    w = mod.factory()
    _select(w, "chrome")
    w._on_use()
    assert started == []                        # no merge started
    assert w._worker is None
    assert "license" in w._status.text().lower()


def test_free_browser_skips_license_write(monkeypatch):
    _app()
    monkeypatch.setattr(mod, "_is_installed", lambda b: False)
    monkeypatch.setattr(mod, "_run", lambda argv: (True, ""))
    monkeypatch.setattr(mod, "InstallWorker", _FakeWorker)
    called = []

    def fake_accept(atom, lics):
        called.append(atom)
        return (True, "")
    monkeypatch.setattr(mod, "set_atom_licenses", fake_accept)

    w = mod.factory()
    _select(w, "firefox")                       # no license → no package.license write
    w._on_use()
    assert called == []
    assert isinstance(w._worker, _FakeWorker)


def test_installed_browser_sets_default_directly(monkeypatch):
    _app()
    calls: list[list[str]] = []

    def fake_run(argv):
        calls.append(argv)
        # report firefox as the current default after a set
        if argv[:2] == ["xdg-settings", "get"]:
            return True, "firefox.desktop"
        return True, ""

    monkeypatch.setattr(mod, "_is_installed", lambda b: True)
    monkeypatch.setattr(mod, "_run", fake_run)
    w = mod.factory()
    assert w._use.text() == "Set as default"
    w._on_use()  # already installed → no worker, straight to xdg-settings set
    assert w._worker is None
    assert ["xdg-settings", "set", "default-web-browser", "firefox.desktop"] in calls
    assert "default browser" in w._status.text()
