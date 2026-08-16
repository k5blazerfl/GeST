"""Users & Groups module: list users, add/delete, set password (via backend)."""

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

from gest.core.users.commands import valid_name
from gest.core.users.reader import groups_for, list_users
from gest.qt.registry import ModuleDescriptor
from gest.qt.users import add_user, delete_user, set_password, user_label

DESCRIPTOR = ModuleDescriptor(
    id="users", title="Users & Groups", category="Users & Security", icon="system-users"
)


class UsersModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._list = QListWidget()
        self._list.setMaximumWidth(260)
        self._groups = QLabel()
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        self._set_pw = QPushButton("Set password")
        self._delete = QPushButton("Delete user")

        # add-user form
        self._new_name = QLineEdit()
        self._new_comment = QLineEdit()
        self._new_groups = QLineEdit()
        self._new_groups.setPlaceholderText("wheel,audio (comma-separated)")
        self._add = QPushButton("Add user")
        self._status = QLabel()

        add_form = QFormLayout()
        add_form.addRow("New user:", self._new_name)
        add_form.addRow("Full name:", self._new_comment)
        add_form.addRow("Groups:", self._new_groups)
        add_form.addRow(self._add)

        pw_row = QHBoxLayout()
        pw_row.addWidget(self._password, 1)
        pw_row.addWidget(self._set_pw)

        right = QVBoxLayout()
        right.addWidget(self._groups)
        right.addLayout(pw_row)
        right.addWidget(self._delete)
        right.addWidget(QLabel("—"))
        right.addLayout(add_form)
        right.addWidget(self._status)
        right.addStretch(1)

        layout = QHBoxLayout(self)
        layout.addWidget(self._list)
        layout.addLayout(right, 1)

        self._list.currentItemChanged.connect(self._load)
        self._set_pw.clicked.connect(self._on_set_pw)
        self._delete.clicked.connect(self._on_delete)
        self._add.clicked.connect(self._on_add)

        self._refresh()

    def _current(self) -> str:
        item = self._list.currentItem()
        return item.data(Qt.UserRole) if item else ""

    def _refresh(self) -> None:
        selected = self._current()
        self._list.clear()
        for user in list_users():
            item = QListWidgetItem(user_label(user), self._list)
            item.setData(Qt.UserRole, user.name)
            if user.name == selected:
                self._list.setCurrentItem(item)
        if self._list.currentItem() is None and self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _load(self, *_args) -> None:
        name = self._current()
        if name:
            self._groups.setText("Groups: " + (", ".join(groups_for(name)) or "—"))

    def _on_set_pw(self) -> None:
        name = self._current()
        if not name or not self._password.text():
            return
        ok, msg = set_password(name, self._password.text())
        self._password.clear()
        self._status.setText("Password set." if ok else f"Failed: {msg}")

    def _on_delete(self) -> None:
        name = self._current()
        if not name:
            return
        ok, msg = delete_user(name)
        self._status.setText(f"Deleted {name}." if ok else f"Failed: {msg}")
        self._refresh()

    def _on_add(self) -> None:
        name = self._new_name.text().strip()
        if not valid_name(name):
            self._status.setText("Invalid user name.")
            return
        ok, msg = add_user(
            name, self._new_comment.text().strip(), groups=self._new_groups.text().strip()
        )
        self._status.setText(f"Added {name}." if ok else f"Failed: {msg}")
        if ok:
            self._new_name.clear()
            self._new_comment.clear()
            self._new_groups.clear()
            self._refresh()


def factory() -> QWidget:
    return UsersModule()
