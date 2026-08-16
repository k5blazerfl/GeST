"""A filterable single-select list module — locale, console keymap and console
font all share this shape (mirrors the urwid ``_ChoiceScreen``): a live filter,
the full list with the current value pre-selected, and one Apply button that
calls a polkit-gated bridge and reports the outcome.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ChoiceModule(QWidget):
    def __init__(
        self,
        *,
        items: list[str],
        current: str,
        apply_fn: Callable[[str], tuple[bool, str]],
        noun: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._items = items
        self._apply_fn = apply_fn
        self._current = current
        self._noun = noun

        self._label = QLabel()
        self._filter = QLineEdit()
        self._filter.setPlaceholderText(f"Filter {noun}s…")
        self._list = QListWidget()
        self._apply = QPushButton(f"Set {noun}")
        self._status = QLabel()

        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        layout.addWidget(self._filter)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._apply)
        layout.addWidget(self._status)

        self._filter.textChanged.connect(self._populate)
        self._apply.clicked.connect(self._on_apply)
        self._refresh_label()
        self._populate()

    def _refresh_label(self) -> None:
        self._label.setText(f"Current {self._noun}: {self._current or '—'}")

    def _populate(self) -> None:
        needle = self._filter.text().strip().lower()
        self._list.clear()
        for name in self._items:
            if needle and needle not in name.lower():
                continue
            item = QListWidgetItem(name, self._list)
            if name == self._current:
                self._list.setCurrentItem(item)

    def _on_apply(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        value = item.text()
        ok, msg = self._apply_fn(value)
        if ok:
            self._current = value
            self._refresh_label()
        self._status.setText("Applied." if ok else f"Failed: {msg}")
