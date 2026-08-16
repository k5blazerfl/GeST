"""Preferences module: the per-user GeST UI prefs (accept mode + timer). These
live in a per-user INI (no backend/root), so they are read/written directly.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gest.core import prefs
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="prefs", title="Preferences", category="Software", icon="preferences-other"
)


class PreferencesModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = QComboBox()
        for value in prefs.ACCEPT_MODES:
            label = prefs.ACCEPT_LABELS[value][0]
            self._mode.addItem(label, value)
        self._mode.setCurrentIndex(prefs.ACCEPT_MODES.index(prefs.accept_mode()))

        self._timer = QSpinBox()
        self._timer.setRange(prefs.TIMER_MIN, prefs.TIMER_MAX)
        self._timer.setSuffix(" s")
        self._timer.setValue(prefs.timer_seconds())
        self._status = QLabel()

        form = QFormLayout()
        form.addRow("When applying changes:", self._mode)
        form.addRow("Countdown timer:", self._timer)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._mode.currentIndexChanged.connect(self._on_mode)
        self._timer.valueChanged.connect(self._on_timer)
        self._sync_timer_enabled()

    def _sync_timer_enabled(self) -> None:
        self._timer.setEnabled(self._mode.currentData() == prefs.TIMER)

    def _on_mode(self, _index: int) -> None:
        try:
            prefs.set_accept_mode(self._mode.currentData())
        except ValueError as e:
            self._status.setText(f"Failed: {e}")
            return
        self._sync_timer_enabled()
        self._status.setText("Saved.")

    def _on_timer(self, value: int) -> None:
        try:
            prefs.set_timer_seconds(value)
        except ValueError as e:
            self._status.setText(f"Failed: {e}")
            return
        self._status.setText("Saved.")


def factory() -> QWidget:
    return PreferencesModule()
