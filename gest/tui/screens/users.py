"""Users & Groups module screen: list, add, modify and delete local accounts.

Reading /etc/passwd + /etc/group is unprivileged; mutations go through the
polkit-gated Users backend. 'g' toggles between the users and groups views.
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Checkbox, DataTable, Header, Input, Label, Static

from gest.core.users import reader
from gest.core.users.backend_client import UsersBackend
from gest.core.users.model import User
from gest.tui.widgets.bracket_button import BracketButton
from gest.tui.widgets.function_bar import FunctionBar


class UserFormScreen(ModalScreen):
    """Modal add/edit form for a user. Dismisses with a dict, or None."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, user: User | None = None) -> None:
        super().__init__()
        self._user = user

    def compose(self) -> ComposeResult:
        editing = self._user is not None
        with Vertical(id="form"):
            yield Label("Edit user" if editing else "Add user", classes="form-title")
            yield Label("Login name")
            yield Input(
                value=self._user.name if editing else "",
                id="f-name", disabled=editing,
            )
            yield Label("Full name")
            yield Input(value=self._user.gecos.split(",")[0] if editing else "", id="f-comment")
            yield Label("Login shell")
            yield Input(value=self._user.shell if editing else "/bin/bash", id="f-shell")
            yield Label("Extra groups (comma-separated)")
            yield Input(id="f-groups")
            if not editing:
                yield Checkbox("System account", value=False, id="f-system")
            with Horizontal(classes="form-buttons"):
                yield BracketButton("Save", id="save")
                yield BracketButton("Cancel", id="cancel")

    def on_bracket_button_pressed(self, event: BracketButton.Pressed) -> None:
        if event.button.id == "save":
            self._save()
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _save(self) -> None:
        data = {
            "name": self.query_one("#f-name", Input).value.strip(),
            "comment": self.query_one("#f-comment", Input).value.strip(),
            "shell": self.query_one("#f-shell", Input).value.strip(),
            "groups": self.query_one("#f-groups", Input).value.strip(),
            "editing": self._user is not None,
        }
        try:
            data["system"] = self.query_one("#f-system", Checkbox).value
        except Exception:
            data["system"] = False
        if not data["name"]:
            self.app.notify("A login name is required.", severity="error")
            return
        self.dismiss(data)


class ConfirmDeleteScreen(ModalScreen):
    """Confirm deleting a user (with optional home removal) or a group."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, message: str, *, offer_remove_home: bool = False) -> None:
        super().__init__()
        self._message = message
        self._offer_remove_home = offer_remove_home

    def compose(self) -> ComposeResult:
        with Vertical(id="form"):
            yield Label(self._message, classes="form-title")
            if self._offer_remove_home:
                yield Checkbox("Also remove home directory", value=False, id="f-rmhome")
            with Horizontal(classes="form-buttons"):
                yield BracketButton("Delete", id="ok")
                yield BracketButton("Cancel", id="cancel")

    def on_bracket_button_pressed(self, event: BracketButton.Pressed) -> None:
        if event.button.id == "ok":
            remove_home = False
            if self._offer_remove_home:
                remove_home = self.query_one("#f-rmhome", Checkbox).value
            self.dismiss({"ok": True, "remove_home": remove_home})
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class UsersScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("f9", "app.pop_screen", "Back"),
        Binding("g", "toggle_view", "Users/Groups"),
        Binding("a", "add", "Add"),
        Binding("e", "edit", "Edit"),
        Binding("d", "delete", "Delete"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._view = "users"
        self._users: dict[str, User] = {}
        self._order: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Users", id="users-title")
        yield Static(" a add · e edit · d delete · g groups · Esc back", id="users-hint")
        table = DataTable(id="users-table", cursor_type="row", zebra_stripes=True)
        yield table
        yield FunctionBar([("F1", "Help"), ("g", "Users/Groups"), ("F9", "Back")])

    def on_mount(self) -> None:
        self.title = "Users and Groups"
        self.query_one("#users-table", DataTable).focus()
        self.load()

    # -- view + load --------------------------------------------------------

    def action_toggle_view(self) -> None:
        self._view = "groups" if self._view == "users" else "users"
        self.query_one("#users-title", Static).update(
            "Groups" if self._view == "groups" else "Users"
        )
        self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        if self._view == "users":
            user_list = reader.list_users()
            rows = [(u.name, str(u.uid), u.full_name, u.shell) for u in user_list]
            users = {u.name: u for u in user_list}
            order = [u.name for u in user_list]
            self.app.call_from_thread(self._fill_users, rows, users, order)
        else:
            rows = [
                (g.name, str(g.gid), ", ".join(g.members))
                for g in reader.list_groups()
            ]
            self.app.call_from_thread(self._fill_groups, rows)

    def _table(self) -> DataTable:
        return self.query_one("#users-table", DataTable)

    def _fill_users(self, rows, users, order) -> None:
        self._users = users
        self._order = order
        table = self._table()
        table.clear(columns=True)
        table.add_columns("Login", "UID", "Full name", "Shell")
        for row in rows:
            table.add_row(*row)

    def _fill_groups(self, rows) -> None:
        self._order = [r[0] for r in rows]
        table = self._table()
        table.clear(columns=True)
        table.add_columns("Group", "GID", "Members")
        for row in rows:
            table.add_row(*row)

    def _current_name(self) -> str | None:
        table = self._table()
        if not self._order or table.cursor_row is None:
            return None
        if 0 <= table.cursor_row < len(self._order):
            return self._order[table.cursor_row]
        return None

    # -- actions ------------------------------------------------------------

    def action_add(self) -> None:
        if self._view == "users":
            self.app.push_screen(UserFormScreen(), self._on_user_form)
        else:
            self.app.push_screen(_GroupFormScreen(), self._on_group_form)

    def action_edit(self) -> None:
        if self._view != "users":
            self.app.notify("Editing groups isn't supported yet.", severity="warning")
            return
        name = self._current_name()
        if name and name in self._users:
            self.app.push_screen(UserFormScreen(self._users[name]), self._on_user_form)

    def action_delete(self) -> None:
        name = self._current_name()
        if not name:
            return
        if self._view == "users":
            self.app.push_screen(
                ConfirmDeleteScreen(f"Delete user “{name}”?", offer_remove_home=True),
                lambda r: self._on_delete_user(name, r),
            )
        else:
            self.app.push_screen(
                ConfirmDeleteScreen(f"Delete group “{name}”?"),
                lambda r: self._on_delete_group(name, r),
            )

    # -- form callbacks -> backend ------------------------------------------

    def _on_user_form(self, data) -> None:
        if not data:
            return
        if data["editing"]:
            self._call(lambda b: b.modify_user(
                data["name"], data["comment"], data["shell"], data["groups"]))
        else:
            self._call(lambda b: b.add_user(
                data["name"], data["comment"], data["shell"], "", data["groups"],
                data["system"]))

    def _on_group_form(self, data) -> None:
        if data:
            self._call(lambda b: b.add_group(data["name"], data["system"]))

    def _on_delete_user(self, name, result) -> None:
        if result and result.get("ok"):
            self._call(lambda b: b.delete_user(name, result["remove_home"]))

    def _on_delete_group(self, name, result) -> None:
        if result and result.get("ok"):
            self._call(lambda b: b.delete_group(name))

    @work(exclusive=True)
    async def _call(self, action) -> None:
        backend = UsersBackend()
        try:
            await backend.connect()
            ok, out = await action(backend)
        except Exception as exc:
            self.app.notify(f"{exc}", severity="error")
            await backend.close()
            return
        await backend.close()
        self.app.notify(
            out or ("done" if ok else "failed"),
            severity="information" if ok else "error",
        )
        self.load()


class _GroupFormScreen(ModalScreen):
    """Modal add form for a group."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="form"):
            yield Label("Add group", classes="form-title")
            yield Label("Group name")
            yield Input(id="f-name")
            yield Checkbox("System group", value=False, id="f-system")
            with Horizontal(classes="form-buttons"):
                yield BracketButton("Save", id="save")
                yield BracketButton("Cancel", id="cancel")

    def on_bracket_button_pressed(self, event: BracketButton.Pressed) -> None:
        if event.button.id == "save":
            name = self.query_one("#f-name", Input).value.strip()
            if not name:
                self.app.notify("A group name is required.", severity="error")
                return
            self.dismiss({"name": name, "system": self.query_one("#f-system", Checkbox).value})
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
