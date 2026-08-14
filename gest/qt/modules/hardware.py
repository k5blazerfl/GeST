"""Hardware module: the live inventory (read-only), via core/hardware."""

from __future__ import annotations

from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from gest.core.hardware.reader import inventory
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(id="hardware", title="Hardware", category="System", icon="cpu")


class HardwareModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        for section in inventory():
            top = QTreeWidgetItem(tree, [section.title])
            for line in section.lines:
                QTreeWidgetItem(top, [line])
            top.setExpanded(True)
        layout.addWidget(tree)


def factory() -> QWidget:
    return HardwareModule()
