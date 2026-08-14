"""Licenses module: global ACCEPT_LICENSE + per-package acceptances."""

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

from gest.core.licenses.model import LicenseEntry
from gest.core.licenses.reader import accept_license, read_all
from gest.qt.licenses import entry_label, set_atom_licenses, set_global_accept
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="licenses", title="Licenses", category="Software", icon="text-x-copying"
)


class LicensesModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._list = QListWidget()
        self._list.setMaximumWidth(300)
        self._global = QLineEdit()
        self._set_global = QPushButton("Set ACCEPT_LICENSE")
        self._atom = QLineEdit()
        self._licenses = QLineEdit()
        self._set_atom = QPushButton("Set / clear atom")
        self._status = QLabel()

        gform = QFormLayout()
        gform.addRow("ACCEPT_LICENSE:", self._global)
        gform.addRow(self._set_global)
        aform = QFormLayout()
        aform.addRow("Package atom:", self._atom)
        aform.addRow("Licenses:", self._licenses)
        aform.addRow(self._set_atom)

        right = QVBoxLayout()
        right.addWidget(QLabel("Global default:"))
        right.addLayout(gform)
        right.addWidget(QLabel("Per-package (empty licenses clears the atom):"))
        right.addLayout(aform)
        right.addWidget(self._status)
        right.addStretch(1)

        layout = QHBoxLayout(self)
        layout.addWidget(self._list)
        layout.addLayout(right, 1)

        self._list.currentItemChanged.connect(self._on_select)
        self._set_global.clicked.connect(self._on_set_global)
        self._set_atom.clicked.connect(self._on_set_atom)
        self._refresh()

    def _refresh(self) -> None:
        self._global.setText(accept_license())
        self._list.clear()
        for entry in read_all():
            item = QListWidgetItem(entry_label(entry), self._list)
            item.setData(Qt.UserRole, entry)

    def _on_select(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        entry: LicenseEntry = current.data(Qt.UserRole)
        self._atom.setText(entry.atom)
        self._licenses.setText(" ".join(entry.licenses))

    def _on_set_global(self) -> None:
        ok, msg = set_global_accept(self._global.text().strip())
        self._status.setText("Applied." if ok else f"Failed: {msg}")

    def _on_set_atom(self) -> None:
        ok, msg = set_atom_licenses(self._atom.text(), self._licenses.text().split())
        self._status.setText("Applied." if ok else f"Failed: {msg}")
        if ok:
            self._refresh()


def factory() -> QWidget:
    return LicensesModule()
