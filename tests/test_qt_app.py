"""Offscreen smoke test for the Control Center (framework, without core readers)."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from gest.qt.app import ControlCenter, embed_window, parse_embed_arg
from gest.qt.registry import ModuleDescriptor, Registry


def _app():
    return QApplication.instance() or QApplication([])


def test_control_center_builds_sidebar_and_activates():
    _app()
    r = Registry()
    r.register(ModuleDescriptor("h", "Hardware", "System"), lambda: QLabel("hw"))
    r.register(ModuleDescriptor("s", "Software", "Software"), lambda: QLabel("sw"))
    cc = ControlCenter(r)

    # two categories, one module each (fake factories → no core readers run)
    assert cc.tree.topLevelItemCount() == 2

    widget = cc.activate("h")
    assert cc.stack.currentWidget() is widget
    # re-activating returns the cached instance
    assert cc.activate("h") is widget


def test_parse_embed_arg():
    assert parse_embed_arg(["--embed", "software"]) == "software"
    assert parse_embed_arg([]) is None
    assert parse_embed_arg(["--embed"]) is None  # missing value


def test_embed_window_hosts_single_module():
    _app()
    r = Registry()
    r.register(ModuleDescriptor("s", "Software", "Software"), lambda: QLabel("sw"))
    win = embed_window(r, "s")
    assert win is not None
    assert "Software" in win.windowTitle()
    assert embed_window(r, "nope") is None
