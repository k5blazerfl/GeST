"""System Logs module: pick a source and view its tail (read-only)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QWidget,
)

from gest.core.logs.reader import list_sources, read_source
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="logs", title="System Logs", category="System", icon="utilities-log-viewer"
)


class LogsModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sources = {s.key: s for s in list_sources()}
        self._list = QListWidget()
        self._list.setMaximumWidth(220)
        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)

        layout = QHBoxLayout(self)
        layout.addWidget(self._list)
        layout.addWidget(self._view, 1)

        for source in self._sources.values():
            item = QListWidgetItem(source.label, self._list)
            item.setData(Qt.UserRole, source.key)
        self._list.currentItemChanged.connect(self._load)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _load(self, *_args) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        source = self._sources.get(item.data(Qt.UserRole))
        if source is None:
            return
        self._view.setPlainText("\n".join(read_source(source)))


def factory() -> QWidget:
    return LogsModule()
