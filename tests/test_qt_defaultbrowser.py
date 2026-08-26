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
