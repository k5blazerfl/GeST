"""Offscreen smoke test for the Control Center (framework, without core readers)."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from gest.qt.app import ControlCenter
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
