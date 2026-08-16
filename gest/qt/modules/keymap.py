"""Console keymap module: pick the console keymap (via the polkit backend)."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from gest.core.system.console import current_keymap, list_keymaps
from gest.qt.modules._choice import ChoiceModule
from gest.qt.registry import ModuleDescriptor
from gest.qt.system import set_keymap

DESCRIPTOR = ModuleDescriptor(
    id="keymap", title="Console Keymap", category="System", icon="input-keyboard"
)


def factory() -> QWidget:
    return ChoiceModule(
        items=list_keymaps(),
        current=current_keymap(),
        apply_fn=set_keymap,
        noun="keymap",
    )
