"""Repositories module: enable/disable/remove/add ebuild repos (via backend)."""

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

from gest.core.repos.reader import disabled_repos, enabled_repos
from gest.qt.registry import ModuleDescriptor
from gest.qt.repos import add, disable, enable, remove, repo_label

DESCRIPTOR = ModuleDescriptor(
    id="repos", title="Repositories", category="Software", icon="folder-remote"
)


class ReposModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._list = QListWidget()
        self._list.setMaximumWidth(240)
        self._enable = QPushButton("Enable")
        self._disable = QPushButton("Disable")
        self._remove = QPushButton("Remove")
        self._status = QLabel()

        self._new_name = QLineEdit()
        self._new_type = QLineEdit("git")
        self._new_uri = QLineEdit()
        self._add = QPushButton("Add repository")

        buttons = QHBoxLayout()
        buttons.addWidget(self._enable)
        buttons.addWidget(self._disable)
        buttons.addWidget(self._remove)
        add_form = QFormLayout()
        add_form.addRow("Name:", self._new_name)
        add_form.addRow("Sync type:", self._new_type)
        add_form.addRow("URI:", self._new_uri)
        add_form.addRow(self._add)

        right = QVBoxLayout()
        right.addLayout(buttons)
        right.addWidget(QLabel("Add a repository:"))
        right.addLayout(add_form)
        right.addWidget(self._status)
        right.addStretch(1)

        layout = QHBoxLayout(self)
        layout.addWidget(self._list)
        layout.addLayout(right, 1)

        self._enable.clicked.connect(lambda: self._act(enable))
        self._disable.clicked.connect(lambda: self._act(disable))
        self._remove.clicked.connect(lambda: self._act(remove))
        self._add.clicked.connect(self._on_add)
        self._refresh()

    def _current(self) -> str:
        item = self._list.currentItem()
        return item.data(Qt.UserRole) if item else ""

    def _refresh(self) -> None:
        selected = self._current()
        self._list.clear()
        for repo in [*enabled_repos(), *disabled_repos()]:
            item = QListWidgetItem(repo_label(repo), self._list)
            item.setData(Qt.UserRole, repo.name)
            if repo.name == selected:
                self._list.setCurrentItem(item)

    def _act(self, fn) -> None:
        name = self._current()
        if not name:
            return
        ok, msg = fn(name)
        self._status.setText("Done." if ok else f"Failed: {msg}")
        self._refresh()

    def _on_add(self) -> None:
        name = self._new_name.text().strip()
        if not name:
            return
        ok, msg = add(name, self._new_type.text().strip() or "git", self._new_uri.text().strip())
        self._status.setText(f"Added {name}." if ok else f"Failed: {msg}")
        if ok:
            self._refresh()


def factory() -> QWidget:
    return ReposModule()
