"""Disks module: a read-only view of block devices and their mount points."""

from __future__ import annotations

from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from gest.core.disk.reader import list_block_devices
from gest.qt.disk import device_label
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(id="disk", title="Disks", category="System", icon="drive-harddisk")


class DiskModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        for dev in list_block_devices():
            QTreeWidgetItem(tree, [device_label(dev)])
        layout.addWidget(tree)


def factory() -> QWidget:
    return DiskModule()
