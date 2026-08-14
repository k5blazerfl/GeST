"""sysctl module: view kernel parameters and set one (via the polkit backend)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.core.sysctl.reader import current_settings
from gest.qt.registry import ModuleDescriptor
from gest.qt.sysctl import apply_settings, merged_settings

DESCRIPTOR = ModuleDescriptor(
    id="sysctl", title="Kernel Parameters", category="System", icon="preferences-system"
)


class SysctlModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._key = QLineEdit()
        self._key.setPlaceholderText("net.ipv4.ip_forward")
        self._value = QLineEdit()
        self._apply = QPushButton("Set")
        self._status = QLabel()

        form = QFormLayout()
        form.addRow("Key:", self._key)
        form.addRow("Value:", self._value)
        row = QHBoxLayout()
        row.addWidget(self._apply)
        row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self._view, 1)
        layout.addLayout(form)
        layout.addLayout(row)
        layout.addWidget(self._status)

        self._apply.clicked.connect(self._on_apply)
        self._refresh()

    def _refresh(self) -> None:
        settings = current_settings()
        self._view.setPlainText("\n".join(f"{k} = {v}" for k, v in sorted(settings.items())))

    def _on_apply(self) -> None:
        key = self._key.text().strip()
        value = self._value.text().strip()
        if not key:
            return
        ok, msg = apply_settings(merged_settings(current_settings(), key, value))
        self._status.setText("Applied." if ok else f"Failed: {msg}")
        self._refresh()


def factory() -> QWidget:
    return SysctlModule()
