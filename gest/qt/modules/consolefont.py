"""Console font module: pick the console font (via the polkit backend)."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from gest.core.system.console import current_font, list_fonts
from gest.qt.modules._choice import ChoiceModule
from gest.qt.registry import ModuleDescriptor
from gest.qt.system import set_console_font

DESCRIPTOR = ModuleDescriptor(
    id="consolefont", title="Console Font", category="System",
    icon="preferences-desktop-font",
)


def factory() -> QWidget:
    return ChoiceModule(
        items=list_fonts(),
        current=current_font(),
        apply_fn=set_console_font,
        noun="console font",
    )
