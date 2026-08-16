"""Privilege module: configure sudo/doas for a group (via the backend)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from gest.core.privilege.reader import available_tools, doas_policy, sudo_policy
from gest.qt.privilege import escalation_summary, set_doas, set_sudo
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="privilege", title="Privilege (sudo/doas)", category="Users & Security", icon="dialog-password"
)


class PrivilegeModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tool = QComboBox()
        self._tool.addItems(available_tools() or ["sudo", "doas"])
        self._group = QLineEdit("wheel")
        self._enabled = QCheckBox("Grant this group escalation")
        self._enabled.setChecked(True)
        self._passwordless = QCheckBox("Passwordless")
        self._apply = QPushButton("Apply")
        self._summary = QLabel()
        self._status = QLabel()

        form = QFormLayout(self)
        form.addRow(self._summary)
        form.addRow("Tool:", self._tool)
        form.addRow("Group:", self._group)
        form.addRow(self._enabled)
        form.addRow(self._passwordless)
        form.addRow(self._apply)
        form.addRow(self._status)

        self._tool.currentTextChanged.connect(self._refresh)
        self._apply.clicked.connect(self._on_apply)
        self._refresh()

    def _refresh(self, *_args) -> None:
        tool = self._tool.currentText()
        policy = sudo_policy() if tool == "sudo" else doas_policy()
        self._summary.setText(escalation_summary(tool, policy))

    def _on_apply(self) -> None:
        tool = self._tool.currentText()
        group = self._group.text().strip() or "wheel"
        enabled = self._enabled.isChecked()
        pw = self._passwordless.isChecked()
        fn = set_sudo if tool == "sudo" else set_doas
        ok, msg = fn(group, enabled, pw)
        self._status.setText("Applied." if ok else f"Failed: {msg}")
        self._refresh()


def factory() -> QWidget:
    return PrivilegeModule()
