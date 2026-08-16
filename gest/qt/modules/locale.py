"""Locale module: pick the system locale from ``locale -a`` (via the polkit backend)."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from gest.core.system.locale import current_locale, list_locales
from gest.qt.modules._choice import ChoiceModule
from gest.qt.registry import ModuleDescriptor
from gest.qt.system import set_locale

DESCRIPTOR = ModuleDescriptor(
    id="locale", title="Locale", category="System", icon="preferences-desktop-locale"
)


def factory() -> QWidget:
    return ChoiceModule(
        items=list_locales(),
        current=current_locale(),
        apply_fn=set_locale,
        noun="locale",
    )
