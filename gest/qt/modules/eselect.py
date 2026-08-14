"""eselect module: browse eselect modules + targets and switch the selection."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.core.eselect.reader import list_modules, list_targets
from gest.qt.eselect import set_target, target_label
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="eselect", title="eselect", category="System", icon="preferences-other"
)


class EselectModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._modules = QListWidget()
        self._modules.setMaximumWidth(200)
        self._targets = QListWidget()
        self._set = QPushButton("Set selected target")
        self._status = QLabel()

        right = QVBoxLayout()
        right.addWidget(self._targets, 1)
        right.addWidget(self._set)
        right.addWidget(self._status)

        layout = QHBoxLayout(self)
        layout.addWidget(self._modules)
        layout.addLayout(right, 1)

        for module in list_modules():
            item = QListWidgetItem(module.name, self._modules)
            item.setData(Qt.UserRole, module.name)
        self._modules.currentItemChanged.connect(self._load_targets)
        self._set.clicked.connect(self._on_set)
        if self._modules.count() > 0:
            self._modules.setCurrentRow(0)

    def _current_module(self) -> str:
        item = self._modules.currentItem()
        return item.data(Qt.UserRole) if item else ""

    def _load_targets(self, *_args) -> None:
        module = self._current_module()
        self._targets.clear()
        if not module:
            return
        for target in list_targets(module):
            item = QListWidgetItem(target_label(target), self._targets)
            item.setData(Qt.UserRole, str(target.number))
            if target.current:
                self._targets.setCurrentItem(item)

    def _on_set(self) -> None:
        module = self._current_module()
        item = self._targets.currentItem()
        if not module or item is None:
            return
        ok, msg = set_target(module, item.data(Qt.UserRole))
        self._status.setText("Switched." if ok else f"Failed: {msg}")
        self._load_targets()


def factory() -> QWidget:
    return EselectModule()
