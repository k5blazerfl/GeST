"""make.conf module: view and set make.conf variables (via the Portage backend)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.core.makeconf.reader import read_makeconf
from gest.qt.makeconf import set_var, var_label
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="makeconf", title="make.conf", category="Software", icon="text-x-generic"
)


class MakeConfModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._list = QListWidget()
        self._list.setMaximumWidth(280)
        self._name = QLineEdit()
        self._value = QLineEdit()
        self._set = QPushButton("Set variable")
        self._status = QLabel()

        form = QFormLayout()
        form.addRow("Name:", self._name)
        form.addRow("Value:", self._value)
        form.addRow(self._set)

        right = QVBoxLayout()
        right.addWidget(QLabel("Select a variable to edit, or type a new one:"))
        right.addLayout(form)
        right.addWidget(self._status)
        right.addStretch(1)

        layout = QHBoxLayout(self)
        layout.addWidget(self._list)
        layout.addLayout(right, 1)

        self._list.currentItemChanged.connect(self._on_select)
        self._set.clicked.connect(self._on_set)
        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        for var in read_makeconf():
            item = QListWidgetItem(var_label(var), self._list)
            item.setData(Qt.UserRole, (var.name, var.value))

    def _on_select(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        name, value = current.data(Qt.UserRole)
        self._name.setText(name)
        self._value.setText(value)

    def _on_set(self) -> None:
        ok, msg = set_var(self._name.text(), self._value.text())
        self._status.setText("Applied." if ok else f"Failed: {msg}")
        if ok:
            self._refresh()


def factory() -> QWidget:
    return MakeConfModule()
