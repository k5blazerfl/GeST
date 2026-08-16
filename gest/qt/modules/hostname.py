"""Hostname module: show the current hostname and set it (via the polkit backend)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.core.system.hostname import current_hostname, valid_hostname
from gest.qt.registry import ModuleDescriptor
from gest.qt.system import set_hostname

DESCRIPTOR = ModuleDescriptor(
    id="hostname", title="Hostname", category="System", icon="preferences-system"
)


class HostnameModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        current = current_hostname()
        self._label = QLabel(f"Current hostname: {current or '—'}")
        self._edit = QLineEdit(current)
        self._edit.setPlaceholderText("my-gentoo-box")
        self._apply = QPushButton("Set hostname")
        self._status = QLabel()

        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        layout.addWidget(self._edit)
        layout.addWidget(self._apply)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._apply.clicked.connect(self._on_apply)

    def _on_apply(self) -> None:
        name = self._edit.text().strip()
        if not valid_hostname(name):
            self._status.setText("Invalid hostname.")
            return
        ok, msg = set_hostname(name)
        if ok:
            self._label.setText(f"Current hostname: {name}")
        self._status.setText("Applied." if ok else f"Failed: {msg}")


def factory() -> QWidget:
    return HostnameModule()
