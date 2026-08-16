"""Hosts file module: add/edit/remove /etc/hosts entries (address → hostnames),
persisted atomically through the polkit-gated Network backend on every change.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
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

from gest.core.network.hosts import (
    HostsEntry,
    current_hosts,
    valid_host_address,
    valid_host_name,
)
from gest.qt.net import set_hosts
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="hosts", title="Hosts File", category="Network", icon="text-x-generic"
)


def _entry_label(entry: HostsEntry) -> str:
    return f"{entry.address}\t{' '.join(entry.names)}"


class _EntryDialog(QDialog):
    """A two-field editor (Address, Hostnames) that only accepts a valid entry."""

    def __init__(self, entry: HostsEntry | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Host entry")
        self._address = QLineEdit(entry.address if entry else "")
        self._address.setPlaceholderText("192.168.1.10")
        self._names = QLineEdit(" ".join(entry.names) if entry else "")
        self._names.setPlaceholderText("host.example.com host")
        self._error = QLabel()

        form = QFormLayout()
        form.addRow("Address:", self._address)
        form.addRow("Hostnames:", self._names)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        entry = self.entry()
        if not valid_host_address(entry.address):
            self._error.setText("Address must be a valid IP.")
            return
        if not entry.names or not all(valid_host_name(n) for n in entry.names):
            self._error.setText("Give at least one valid hostname.")
            return
        self.accept()

    def entry(self) -> HostsEntry:
        return HostsEntry(
            address=self._address.text().strip(),
            names=self._names.text().split(),
        )


class HostsModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[HostsEntry] = list(current_hosts())
        self._list = QListWidget()
        add = QPushButton("Add…")
        edit = QPushButton("Edit…")
        remove = QPushButton("Remove")
        self._status = QLabel()

        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(edit)
        buttons.addWidget(remove)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self._list, 1)
        layout.addLayout(buttons)
        layout.addWidget(self._status)

        add.clicked.connect(self._on_add)
        edit.clicked.connect(self._on_edit)
        remove.clicked.connect(self._on_remove)
        self._populate()

    def _populate(self) -> None:
        self._list.clear()
        for entry in self._entries:
            QListWidgetItem(_entry_label(entry), self._list)

    def _persist(self) -> None:
        payload = [(e.address, e.names) for e in self._entries]
        ok, msg = set_hosts(payload)
        self._status.setText("Saved." if ok else f"Failed: {msg}")
        if ok:
            self._populate()

    def _on_add(self) -> None:
        dialog = _EntryDialog(None, self)
        if dialog.exec() == QDialog.Accepted:
            self._entries.append(dialog.entry())
            self._persist()

    def _on_edit(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        dialog = _EntryDialog(self._entries[row], self)
        if dialog.exec() == QDialog.Accepted:
            self._entries[row] = dialog.entry()
            self._persist()

    def _on_remove(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        del self._entries[row]
        self._persist()


def factory() -> QWidget:
    return HostsModule()
