"""env.d module: view /etc/env.d variables and set one (via the backend)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.core.envd.reader import current_vars
from gest.qt.envd import apply_vars
from gest.qt.registry import ModuleDescriptor
from gest.qt.sysctl import merged_settings  # generic current+{k:v} merge

DESCRIPTOR = ModuleDescriptor(
    id="envd", title="Environment", category="System", icon="preferences-system"
)


class EnvdModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._key = QLineEdit()
        self._key.setPlaceholderText("EDITOR")
        self._value = QLineEdit()
        self._apply = QPushButton("Set")
        self._status = QLabel()

        form = QFormLayout()
        form.addRow("Variable:", self._key)
        form.addRow("Value:", self._value)
        form.addRow(self._apply)

        layout = QVBoxLayout(self)
        layout.addWidget(self._view, 1)
        layout.addLayout(form)
        layout.addWidget(self._status)

        self._apply.clicked.connect(self._on_apply)
        self._refresh()

    def _refresh(self) -> None:
        self._view.setPlainText(
            "\n".join(f"{k} = {v}" for k, v in sorted(current_vars().items()))
        )

    def _on_apply(self) -> None:
        key = self._key.text().strip()
        if not key:
            return
        ok, msg = apply_vars(merged_settings(current_vars(), key, self._value.text().strip()))
        self._status.setText("Applied." if ok else f"Failed: {msg}")
        self._refresh()


def factory() -> QWidget:
    return EnvdModule()
