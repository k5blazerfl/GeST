"""Users & Groups in urwid: list users/groups + modal add/edit/delete forms.

Reads /etc/passwd + /etc/group unprivileged; mutations go through the async
UsersBackend. 'g' toggles the users/groups view.
"""

from __future__ import annotations

import urwid

from gest.core.users import reader
from gest.core.users.backend_client import UsersBackend
from gest.core.users.model import User
from gest.uwui.runtime import App, Screen


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


class Modal(urwid.WidgetWrap):
    """A form modal: title, body rows, and a centered row of buttons.

    ``buttons`` is ``[(label, callback), …]``; Esc cancels (pops the overlay).
    """

    def __init__(self, app: App, title: str, rows: list, buttons: list):
        self.app = app
        button_widgets = [
            urwid.AttrMap(urwid.Button(label, on_press=lambda _b, cb=cb: cb()),
                          None, focus_map="focus")
            for label, cb in buttons
        ]
        grid = urwid.GridFlow(button_widgets, cell_width=16, h_sep=2, v_sep=1,
                              align="center")
        pile = urwid.Pile(
            [urwid.Text(("title", title)), urwid.Divider(), *rows,
             urwid.Divider(), grid]
        )
        super().__init__(urwid.Filler(pile, valign="top"))

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if key == "esc":
            self.app.pop()
            return None
        return key


class UsersScreen(Screen):
    def __init__(self, app: App) -> None:
        self._view = "users"
        self._users: dict[str, User] = {}
        self._order: list[str] = []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        self._box = urwid.LineBox(self._list, title="Users")
        super().__init__(
            app, self._box, title="Users and Groups",
            footer_keys=[
                ("Enter/a", "Add"), ("e", "Edit"), ("d", "Delete"),
                ("p", "Passwd"), ("m", "Member"), ("g", "Groups"), ("Esc", "Back"),
            ],
        )
        app.run_async(self._load())

    # -- loading ------------------------------------------------------------

    async def _load(self) -> None:
        if self._view == "users":
            users = await self.app.run_blocking(reader.list_users)
            self._users = {u.name: u for u in users}
            self._order = [u.name for u in users]
            rows = [_row(f"{u.name:<18} {u.uid:<7} {u.full_name:<22} {u.shell}")
                    for u in users]
            self._box.set_title("Users")
        else:
            groups = await self.app.run_blocking(reader.list_groups)
            self._order = [g.name for g in groups]
            rows = [_row(f"{g.name:<20} {g.gid:<7} {', '.join(g.members)}")
                    for g in groups]
            self._box.set_title("Groups")
        self._walker[:] = rows or [urwid.Text(" (empty)")]
        if self._order:
            self._walker.set_focus(0)
        self.app.refresh()

    def _current(self) -> str | None:
        if not self._order:
            return None
        return self._order[self._walker.focus]

    async def _call(self, action) -> None:
        backend = UsersBackend()
        try:
            await backend.connect()
            ok, out = await action(backend)
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        self.app.notify(out or ("done" if ok else "failed"), error=not ok)
        await self._load()

    # -- key handling -------------------------------------------------------

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
        elif key == "g":
            self._view = "groups" if self._view == "users" else "users"
            self.app.run_async(self._load())
        elif key in ("a", "enter"):
            self._add()
        elif key == "e":
            self._edit()
        elif key == "d":
            self._delete()
        elif key == "p":
            self._password()
        elif key == "m":
            self._member()
        else:
            return key
        return None

    # -- forms --------------------------------------------------------------

    def _add(self) -> None:
        if self._view == "groups":
            name = urwid.Edit("Group name: ")
            system = urwid.CheckBox("System group")

            def save():
                n = name.edit_text.strip()
                if not n:
                    self.app.notify("A group name is required.", error=True)
                    return
                self.app.pop()
                self.app.run_async(self._call(lambda b: b.add_group(n, system.state)))

            self._open("Add group", [name, system], save)
            return
        name = urwid.Edit("Login name: ")
        comment = urwid.Edit("Full name: ")
        shell = urwid.Edit("Shell: ", "/bin/bash")
        groups = urwid.Edit("Extra groups: ")
        system = urwid.CheckBox("System account")

        def save():
            n = name.edit_text.strip()
            if not n:
                self.app.notify("A login name is required.", error=True)
                return
            self.app.pop()
            self.app.run_async(self._call(
                lambda b: b.add_user(n, comment.edit_text.strip(),
                                     shell.edit_text.strip(), "",
                                     groups.edit_text.strip(), system.state)))

        self._open("Add user", [name, comment, shell, groups, system], save)

    def _edit(self) -> None:
        if self._view != "users":
            self.app.notify("Editing groups isn't supported.", error=True)
            return
        name = self._current()
        if not name or name not in self._users:
            return
        user = self._users[name]
        current_groups = ",".join(reader.groups_for(name))
        comment = urwid.Edit("Full name: ", user.full_name)
        shell = urwid.Edit("Shell: ", user.shell)
        groups = urwid.Edit("Extra groups: ", current_groups)

        def save():
            self.app.pop()
            self.app.run_async(self._call(
                lambda b: b.modify_user(name, comment.edit_text.strip(),
                                        shell.edit_text.strip(),
                                        groups.edit_text.strip())))

        self._open(f"Edit user: {name}", [comment, shell, groups], save)

    def _delete(self) -> None:
        name = self._current()
        if not name:
            return
        if self._view == "users":
            rmhome = urwid.CheckBox("Also remove home directory")

            def do():
                self.app.pop()
                self.app.run_async(self._call(lambda b: b.delete_user(name, rmhome.state)))

            self._confirm(f"Delete user “{name}”?", [rmhome], do)
        else:
            def do():
                self.app.pop()
                self.app.run_async(self._call(lambda b: b.delete_group(name)))

            self._confirm(f"Delete group “{name}”?", [], do)

    def _password(self) -> None:
        if self._view != "users":
            return
        name = self._current()
        if not name:
            return
        pw = urwid.Edit("New password: ", mask="*")
        pw2 = urwid.Edit("Confirm: ", mask="*")

        def save():
            if not pw.edit_text:
                self.app.notify("Password cannot be empty.", error=True)
                return
            if pw.edit_text != pw2.edit_text:
                self.app.notify("Passwords do not match.", error=True)
                return
            secret = pw.edit_text
            self.app.pop()
            self.app.run_async(self._call(lambda b: b.set_password(name, secret)))

        self._open(f"Set password for {name}", [pw, pw2], save)

    def _member(self) -> None:
        if self._view != "groups":
            self.app.notify("Switch to the groups view (g) to edit members.", error=True)
            return
        group = self._current()
        if not group:
            return
        user = urwid.Edit("User: ")

        def act(add: bool):
            u = user.edit_text.strip()
            if not u:
                self.app.notify("A user name is required.", error=True)
                return
            self.app.pop()
            self.app.run_async(self._call(lambda b: b.set_group_member(group, u, add)))

        modal = Modal(
            self.app, f"Group “{group}” — add/remove member", [user],
            [("Add", lambda: act(True)), ("Remove", lambda: act(False)),
             ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 60), height=("relative", 45))

    # -- modal helpers ------------------------------------------------------

    def _open(self, title: str, rows: list, save) -> None:
        modal = Modal(self.app, title, rows, [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 70), height=("relative", 60))

    def _confirm(self, message: str, rows: list, do) -> None:
        modal = Modal(self.app, message, rows, [("Delete", do), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 60), height=("relative", 45))
