"""Date & Time module: show the clock/timezone/NTP status; set the time."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.core.datetime.commands import valid_datetime
from gest.core.datetime.reader import clock_info
from gest.qt.clock import clock_summary, set_clock
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="datetime", title="Date & Time", category="System", icon="preferences-system-time"
)


class ClockModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._info = QLabel()
        self._time = QLineEdit()
        self._time.setPlaceholderText("YYYY-MM-DD HH:MM:SS")
        self._set = QPushButton("Set time")
        self._status = QLabel()

        row = QHBoxLayout()
        row.addWidget(self._time, 1)
        row.addWidget(self._set)
        form = QFormLayout()
        form.addRow("Set clock:", self._wrap(row))

        layout = QVBoxLayout(self)
        layout.addWidget(self._info)
        layout.addLayout(form)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._set.clicked.connect(self._on_set)
        self._refresh()

    @staticmethod
    def _wrap(layout: QHBoxLayout) -> QWidget:
        w = QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        w.setLayout(layout)
        return w

    def _refresh(self) -> None:
        info = clock_info()
        self._info.setText("\n".join(f"{k}: {v}" for k, v in clock_summary(info)))
        if not self._time.text():
            self._time.setText(info.local_time)

    def _on_set(self) -> None:
        text = self._time.text().strip()
        if not valid_datetime(text):
            self._status.setText("Need a timestamp like 2026-08-14 15:30:00")
            return
        ok, msg = set_clock(text)
        self._status.setText("Clock set." if ok else f"Failed: {msg}")
        self._refresh()


def factory() -> QWidget:
    return ClockModule()
