"""Services module (OpenRC): start/stop/restart + enable, via the polkit backend."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.core.services.model import Service
from gest.core.services.reader import list_services
from gest.qt.registry import ModuleDescriptor
from gest.qt.services import control, service_label, set_enabled

DESCRIPTOR = ModuleDescriptor(
    id="services", title="Services", category="Services", icon="applications-utilities"
)


class ServicesModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._services: dict[str, Service] = {}

        self._list = QListWidget()
        self._list.setMaximumWidth(240)

        self._title = QLabel()
        self._start = QPushButton("Start")
        self._stop = QPushButton("Stop")
        self._restart = QPushButton("Restart")
        self._enabled = QCheckBox("Start at boot (enabled)")
        self._status = QLabel()

        buttons = QHBoxLayout()
        buttons.addWidget(self._start)
        buttons.addWidget(self._stop)
        buttons.addWidget(self._restart)
        right = QVBoxLayout()
        right.addWidget(self._title)
        right.addLayout(buttons)
        right.addWidget(self._enabled)
        right.addWidget(self._status)
        right.addStretch(1)

        layout = QHBoxLayout(self)
        layout.addWidget(self._list)
        layout.addLayout(right, 1)

        self._list.currentItemChanged.connect(self._load)
        self._start.clicked.connect(lambda: self._control("start"))
        self._stop.clicked.connect(lambda: self._control("stop"))
        self._restart.clicked.connect(lambda: self._control("restart"))
        self._enabled.clicked.connect(self._toggle_enabled)

        self._refresh()

    def _current(self) -> str:
        item = self._list.currentItem()
        return item.data(Qt.UserRole) if item else ""

    def _refresh(self) -> None:
        selected = self._current()
        self._list.clear()
        self._services.clear()
        for service in list_services():
            self._services[service.name] = service
            item = QListWidgetItem(service_label(service), self._list)
            item.setData(Qt.UserRole, service.name)
            if service.name == selected:
                self._list.setCurrentItem(item)
        if self._list.currentItem() is None and self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _load(self, *_args) -> None:
        name = self._current()
        service = self._services.get(name)
        if service is None:
            return
        self._title.setText(f"{service.name} — {service.status}")
        self._enabled.setChecked(service.enabled)

    def _control(self, action: str) -> None:
        name = self._current()
        if not name:
            return
        ok, msg = control(name, action)
        self._status.setText(f"{action}: {'ok' if ok else 'failed'}{(' — ' + msg) if msg else ''}")
        self._refresh()

    def _toggle_enabled(self) -> None:
        name = self._current()
        if not name:
            return
        ok, msg = set_enabled(name, self._enabled.isChecked())
        self._status.setText(f"{'enabled' if self._enabled.isChecked() else 'disabled'}: "
                             f"{'ok' if ok else 'failed'}{(' — ' + msg) if msg else ''}")
        self._refresh()


def factory() -> QWidget:
    return ServicesModule()
