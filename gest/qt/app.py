"""gest-settings — the standalone GeST Control Center (PySide6)."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from gest.qt.registry import Registry


class ControlCenter(QWidget):
    """A category tree + a stacked module pane (YaST / System-Settings shape)."""

    def __init__(self, registry: Registry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("GeST — Control Center")
        self.resize(820, 560)
        self._registry = registry
        self._widgets: dict[str, QWidget] = {}  # id -> instantiated widget (cache)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMaximumWidth(240)
        self.stack = QStackedWidget()
        self.stack.addWidget(QLabel("Select a module.", alignment=Qt.AlignCenter))

        layout = QHBoxLayout(self)
        layout.addWidget(self.tree)
        layout.addWidget(self.stack, 1)

        for category, entries in registry.by_category().items():
            cat = QTreeWidgetItem(self.tree, [category])
            cat.setExpanded(True)
            cat.setFlags(cat.flags() & ~Qt.ItemIsSelectable)
            for entry in entries:
                item = QTreeWidgetItem(cat, [entry.descriptor.title])
                item.setData(0, Qt.UserRole, entry.descriptor.id)

        self.tree.currentItemChanged.connect(self._on_selected)

    def _on_selected(self, current: QTreeWidgetItem | None, _previous) -> None:
        if current is None:
            return
        module_id = current.data(0, Qt.UserRole)
        if module_id:
            self.activate(module_id)

    def activate(self, module_id: str) -> QWidget:
        """Lazily build (once) and show a module; returns its widget."""
        if module_id not in self._widgets:
            entry = next(e for e in self._registry.entries() if e.descriptor.id == module_id)
            widget = entry.factory()
            self._widgets[module_id] = widget
            self.stack.addWidget(widget)
        self.stack.setCurrentWidget(self._widgets[module_id])
        return self._widgets[module_id]

    def select_first(self) -> None:
        for i in range(self.tree.topLevelItemCount()):
            cat = self.tree.topLevelItem(i)
            if cat.childCount() > 0:
                self.tree.setCurrentItem(cat.child(0))
                return


def build_registry() -> Registry:
    from gest.qt.modules import hardware, software

    registry = Registry()
    registry.register(hardware.DESCRIPTOR, hardware.factory)
    registry.register(software.DESCRIPTOR, software.factory)
    return registry


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("gest-settings")
    window = ControlCenter(build_registry())
    window.select_first()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
