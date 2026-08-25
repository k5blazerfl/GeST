"""Panel Layout module: the Qt-free launch helper + registration.

Like the other Qt-module tests, the widget itself isn't driven (it shells out to
a GUI); we cover the pure launch-command helper and assert the module registers
into the shared taxonomy under Personalization with an icon hint.
"""

import pytest

from gest.qt.panel import PANEL_EDITOR, panel_editor_command


def test_panel_editor_command_launches_helm_barnacle():
    assert PANEL_EDITOR == "helm-barnacle"
    assert panel_editor_command() == ["helm-barnacle"]


def test_panel_module_registers_under_personalization():
    pytest.importorskip("PySide6")  # build_registry imports every QWidget module
    from gest.qt.app import build_registry

    by_id = {e.descriptor.id: e.descriptor for e in build_registry().entries()}
    assert "panel" in by_id, "panel module is not registered"
    assert by_id["panel"].category == "Personalization"
    assert by_id["panel"].title == "Panel Layout"
    assert by_id["panel"].icon  # the rail renders QIcon.fromTheme(icon)
