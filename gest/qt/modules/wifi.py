"""Wi-Fi module: list configured networks; add/remove (via the backend)."""

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

from gest.core.wifi.reader import configured_networks
from gest.qt.registry import ModuleDescriptor
from gest.qt.wifi import add_network, remove_network, wifi_label

DESCRIPTOR = ModuleDescriptor(id="wifi", title="Wi-Fi", category="Network", icon="network-wireless")


class WifiModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._list = QListWidget()
        self._list.setMaximumWidth(240)
        self._remove = QPushButton("Remove")
        self._ssid = QLineEdit()
        self._psk = QLineEdit()
        self._psk.setEchoMode(QLineEdit.Password)
        self._add = QPushButton("Add network")
        self._status = QLabel()

        form = QFormLayout()
        form.addRow("SSID:", self._ssid)
        form.addRow("Passphrase:", self._psk)
        form.addRow(self._add)

        right = QVBoxLayout()
        right.addWidget(self._remove)
        right.addWidget(QLabel("Add a network:"))
        right.addLayout(form)
        right.addWidget(self._status)
        right.addStretch(1)

        layout = QHBoxLayout(self)
        layout.addWidget(self._list)
        layout.addLayout(right, 1)

        self._remove.clicked.connect(self._on_remove)
        self._add.clicked.connect(self._on_add)
        self._refresh()

    def _current(self) -> str:
        item = self._list.currentItem()
        return item.data(Qt.UserRole) if item else ""

    def _refresh(self) -> None:
        self._list.clear()
        for net in configured_networks():
            item = QListWidgetItem(wifi_label(net), self._list)
            item.setData(Qt.UserRole, net.ssid)

    def _on_remove(self) -> None:
        ssid = self._current()
        if not ssid:
            return
        ok, msg = remove_network(ssid)
        self._status.setText(f"Removed {ssid}." if ok else f"Failed: {msg}")
        self._refresh()

    def _on_add(self) -> None:
        ssid = self._ssid.text().strip()
        if not ssid:
            return
        ok, msg = add_network(ssid, self._psk.text())
        self._status.setText(f"Added {ssid}." if ok else f"Failed: {msg}")
        if ok:
            self._ssid.clear()
            self._psk.clear()
            self._refresh()


def factory() -> QWidget:
    return WifiModule()
