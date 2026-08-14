"""Network module: view interfaces and set DHCP/static (widget → core → backend).

The first *mutating* module — writes go through the polkit-gated Network backend,
exactly as the TUI does.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
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

from gest.core.network.reader import list_interfaces, read_interface_config
from gest.qt.net import apply_interface_config, set_link, validate_static
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="network", title="Network", category="Network", icon="network-wired"
)


class NetworkModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._up: dict[str, bool] = {}

        self._list = QListWidget()
        self._list.setMaximumWidth(200)

        self._method = QComboBox()
        self._method.addItems(["dhcp", "static"])
        self._address = QLineEdit()
        self._address.setPlaceholderText("192.168.1.10/24")
        self._gateway = QLineEdit()
        self._gateway.setPlaceholderText("192.168.1.1 (optional)")
        self._apply = QPushButton("Apply")
        self._link = QPushButton("Bring up / down")
        self._status = QLabel()

        form = QFormLayout()
        form.addRow("Method:", self._method)
        form.addRow("Address:", self._address)
        form.addRow("Gateway:", self._gateway)
        row = QHBoxLayout()
        row.addWidget(self._apply)
        row.addWidget(self._link)
        right = QVBoxLayout()
        right.addLayout(form)
        right.addLayout(row)
        right.addWidget(self._status)
        right.addStretch(1)

        layout = QHBoxLayout(self)
        layout.addWidget(self._list)
        layout.addLayout(right, 1)

        self._method.currentTextChanged.connect(self._sync_enabled)
        self._list.currentItemChanged.connect(self._load)
        self._apply.clicked.connect(self._on_apply)
        self._link.clicked.connect(self._on_link)

        self._refresh()

    def _current_iface(self) -> str:
        item = self._list.currentItem()
        return item.data(Qt.UserRole) if item else ""

    def _refresh(self) -> None:
        selected = self._current_iface()
        self._list.clear()
        self._up.clear()
        for iface in list_interfaces():
            if iface.loopback:
                continue
            self._up[iface.name] = iface.up
            item = QListWidgetItem(f"{iface.name} — {'up' if iface.up else 'down'}", self._list)
            item.setData(Qt.UserRole, iface.name)
            if iface.name == selected:
                self._list.setCurrentItem(item)
        if self._list.currentItem() is None and self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _load(self, *_args) -> None:
        iface = self._current_iface()
        if not iface:
            return
        cfg = read_interface_config(iface)
        self._method.setCurrentText(cfg.method if cfg.method in ("dhcp", "static") else "dhcp")
        self._address.setText(cfg.address)
        self._gateway.setText(cfg.gateway)
        self._sync_enabled()

    def _sync_enabled(self) -> None:
        static = self._method.currentText() == "static"
        self._address.setEnabled(static)
        self._gateway.setEnabled(static)

    def _on_apply(self) -> None:
        iface = self._current_iface()
        if not iface:
            return
        method = self._method.currentText()
        address = self._address.text().strip()
        gateway = self._gateway.text().strip()
        if method == "static":
            err = validate_static(address, gateway)
            if err:
                self._status.setText(err)
                return
        ok, msg = apply_interface_config(iface, method, address, gateway)
        self._status.setText("Applied." if ok else f"Failed: {msg}")

    def _on_link(self) -> None:
        iface = self._current_iface()
        if not iface:
            return
        ok, msg = set_link(iface, not self._up.get(iface, False))
        self._status.setText("Done." if ok else f"Failed: {msg}")
        if ok:
            self._refresh()


def factory() -> QWidget:
    return NetworkModule()
