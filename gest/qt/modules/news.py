"""Portage News module: list news items, read one (marks it read), and
mark-all-read — via the polkit-gated backend.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.core.software.news import list_news, parse_content, read_news
from gest.qt.registry import ModuleDescriptor
from gest.qt.software import format_news_content, mark_news_read, news_item_label

DESCRIPTOR = ModuleDescriptor(
    id="news", title="Portage News", category="Software", icon="mail-message-new"
)


class NewsModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._list = QListWidget()
        self._content = QPlainTextEdit()
        self._content.setReadOnly(True)
        mark_all = QPushButton("Mark all read")
        self._status = QLabel()

        left = QVBoxLayout()
        left.addWidget(self._list, 1)
        left.addWidget(mark_all)
        right = QVBoxLayout()
        right.addWidget(self._content, 1)
        right.addWidget(self._status)

        layout = QHBoxLayout(self)
        layout.addLayout(left, 1)
        layout.addLayout(right, 2)

        self._list.currentItemChanged.connect(self._on_select)
        mark_all.clicked.connect(self._on_mark_all)
        self._reload()

    def _reload(self) -> None:
        self._list.clear()
        for item in list_news():
            row = QListWidgetItem(news_item_label(item), self._list)
            row.setData(Qt.UserRole, item.number)
            row.setData(Qt.UserRole + 1, item.unread)

    def _on_select(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        number = current.data(Qt.UserRole)
        self._content.setPlainText(format_news_content(parse_content(read_news(number))))
        if current.data(Qt.UserRole + 1):  # was unread → mark it read
            ok, msg = mark_news_read(str(number))
            self._status.setText("Marked read." if ok else f"Failed: {msg}")
            if ok:
                self._reload()

    def _on_mark_all(self) -> None:
        ok, msg = mark_news_read("all")
        self._status.setText("All marked read." if ok else f"Failed: {msg}")
        if ok:
            self._reload()


def factory() -> QWidget:
    return NewsModule()
