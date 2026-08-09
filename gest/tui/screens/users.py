"""Users & Groups in urwid: a YaST-style tabbed admin screen.

Four tabs — Users, Groups, Defaults for New Users, Authentication — switched
with ←/→ (g toggles Users⇄Groups). Users/Groups are columnar tables with add/
edit/delete/password/member modals; Defaults and Authentication are read-only
status views (parsed from /etc/default/useradd + /etc/login.defs and
/etc/nsswitch.conf respectively). Reads are unprivileged; mutations go through
the async UsersBackend.
"""

from __future__ import annotations

import urwid

from gest.core.users import auth, defaults, reader
from gest.core.users.backend_client import UsersBackend
from gest.core.users.model import User
from gest.tui.runtime import App, Modal, Screen

# Column widths (characters); the last column takes the rest and is clipped.
_U_LOGIN, _U_UID, _U_NAME = 18, 8, 24
_G_NAME, _G_GID = 22, 8

# Account filter (YaST-style): human logins live in [1000, 65534); everything
# else (uid < 1000 daemons/services, plus nobody at 65534) is a system account.
_LOCAL_MIN, _NOBODY = 1000, 65534
_FILTERS = ["local", "system", "all"]


def _is_local(xid: int) -> bool:
    return _LOCAL_MIN <= xid < _NOBODY


def _passes(xid: int, flt: str) -> bool:
    if flt == "all":
        return True
    return _is_local(xid) if flt == "local" else not _is_local(xid)


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width - 1 else text[: width - 2] + "…"


def _fmt_user(login: str, uid: str, name: str, groups: str) -> str:
    return (f"{_clip(login, _U_LOGIN):<{_U_LOGIN}}{uid:<{_U_UID}}"
            f"{_clip(name, _U_NAME):<{_U_NAME}}{groups}")


def _fmt_group(name: str, gid: str, members: str) -> str:
    return f"{_clip(name, _G_NAME):<{_G_NAME}}{gid:<{_G_GID}}{members}"


def _row(text: str) -> urwid.Widget:
    icon = urwid.SelectableIcon(text, 0)
    icon.set_wrap_mode("clip")   # one line per row so columns stay aligned
    return urwid.AttrMap(icon, None, focus_map="focus")


def _kv(label: str, value: str) -> urwid.Widget:
    return urwid.Text([("field", f" {label:<32}"), value or "—"], wrap="clip")


class UsersScreen(Screen):
    _TABS = [
        ("users", "Users"),
        ("groups", "Groups"),
        ("defaults", "Defaults for New Users"),
        ("auth", "Authentication"),
    ]

    def __init__(self, app: App) -> None:
        self._view = "users"
        self._filter = "local"   # default to real login accounts, not services
        self._loads = 0          # completed loads (for tests to await)
        self._users: dict[str, User] = {}
        self._order: list[str] = []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)

        self._tabbar = urwid.Text("")
        self._content = urwid.WidgetPlaceholder(self._list_box("users"))
        body = urwid.Pile([
            ("pack", urwid.AttrMap(self._tabbar, "menubar")),
            ("pack", urwid.Divider()),
            ("weight", 1, self._content),
        ])
        super().__init__(
            app, body, title="User and Group Administration",
            footer_keys=[
                ("←/→", "Tabs"), ("f", "Filter"), ("a", "Add"), ("e", "Edit"),
                ("d", "Delete"), ("p", "Passwd"), ("m", "Member"), ("g", "Usr/Grp"),
                ("Esc", "Back"),
            ],
            help_text=(
                "User and group administration, in four tabs (←/→ to switch;\n"
                "g toggles Users ⇄ Groups):\n\n"
                "Users / Groups — add, edit, delete, set passwords, and manage\n"
                "  group membership. The Groups column shows each user's primary\n"
                "  group plus any supplementary groups. On the Users tab, f\n"
                "  cycles the filter: local human accounts → system/service\n"
                "  accounts → all. Groups are always shown in full.\n"
                "Defaults for New Users — the settings applied to new accounts\n"
                "  (from /etc/default/useradd and /etc/login.defs). Read-only.\n"
                "Authentication — which back-ends resolve accounts, parsed from\n"
                "  /etc/nsswitch.conf (SSSD/LDAP/NIS/Winbind). Read-only status.\n\n"
                "a  add    e  edit    d  delete    p  set password    m  member"
            ),
        )
        self._render_tabs()
        app.run_async(self._load())

    # -- tab chrome ---------------------------------------------------------

    def _render_tabs(self) -> None:
        parts: list = [" "]
        for i, (key, label) in enumerate(self._TABS):
            if i:
                parts.append(("dim", "  │  "))
            chip = f" {label} "
            parts.append(("menu_focus", chip) if key == self._view else chip)
        self._tabbar.set_text(parts)

    def _cycle(self, delta: int) -> None:
        keys = [k for k, _ in self._TABS]
        self._view = keys[(keys.index(self._view) + delta) % len(keys)]
        self._show_tab()

    def _show_tab(self) -> None:
        self._render_tabs()
        if self._view in ("users", "groups"):
            self._content.original_widget = self._list_box(self._view)
            self.app.run_async(self._load())
        elif self._view == "defaults":
            self._content.original_widget = urwid.LineBox(
                urwid.ListBox(urwid.SimpleListWalker([urwid.Text(" loading …")])),
                title="Defaults for New Users")
            self.app.run_async(self._load_defaults())
        else:
            self._content.original_widget = urwid.LineBox(
                urwid.ListBox(urwid.SimpleListWalker([urwid.Text(" loading …")])),
                title="Authentication settings")
            self.app.run_async(self._load_auth())

    def _list_box(self, view: str) -> urwid.Widget:
        if view == "users":
            title = f"Users — filter: {self._filter}"
            header = _fmt_user("Login", "UID", "Name", "Groups")
        else:
            title = "Groups"   # groups are always shown in full
            header = _fmt_group("Group", "GID", "Members")
        hdr = urwid.AttrMap(urwid.Text(header, wrap="clip"), "pane_title")
        inner = urwid.Pile([
            ("pack", hdr), ("pack", urwid.Divider("─")), ("weight", 1, self._list),
        ])
        return urwid.LineBox(inner, title=title)

    # -- loading ------------------------------------------------------------

    async def _load(self) -> None:
        if self._view == "users":
            users = await self.app.run_blocking(reader.list_users)
            groups = await self.app.run_blocking(reader.list_groups)
            users = [u for u in users if _passes(u.uid, self._filter)]
            gid_name = {g.gid: g.name for g in groups}
            self._users = {u.name: u for u in users}
            self._order = [u.name for u in users]
            rows = [_row(_fmt_user(u.name, str(u.uid), u.full_name,
                                   self._group_summary(u, gid_name, groups)))
                    for u in users]
        else:
            groups = await self.app.run_blocking(reader.list_groups)
            self._order = [g.name for g in groups]
            rows = [_row(_fmt_group(g.name, str(g.gid), ", ".join(g.members)))
                    for g in groups]
        empty = f" (no {self._filter} users)" if self._view == "users" else " (no groups)"
        self._walker[:] = rows or [urwid.Text(empty)]
        if self._order:
            self._walker.set_focus(0)
        self._loads += 1
        self.app.refresh()

    @staticmethod
    def _group_summary(user: User, gid_name: dict[int, str], groups: list) -> str:
        primary = gid_name.get(user.gid, str(user.gid))
        supp = reader.member_groups(user.name, groups)
        return ", ".join([primary, *[g for g in supp if g != primary]])

    async def _load_defaults(self) -> None:
        d = await self.app.run_blocking(defaults.read_defaults)
        groups = await self.app.run_blocking(reader.list_groups)
        readable = await self.app.run_blocking(defaults.useradd_readable)
        # /etc/default/useradd is typically root-only; show that honestly
        # rather than an empty value that reads as "unset".
        unread = "(requires root)"

        def ua(value: str) -> str:
            return value or (unread if not readable else "—")

        group = d.group
        if group.isdigit():   # useradd stores the primary group as a gid
            gid_name = {str(g.gid): g.name for g in groups}
            group = f"{gid_name.get(group, group)} ({group})"
        rows = [
            urwid.Text(("hint", " Settings applied to newly-created users")),
            urwid.Divider(),
            _kv("Default group", ua(group)),
            _kv("Default login shell", ua(d.shell)),
            _kv("Home directory prefix", ua(d.home)),
            _kv("Umask for home directory", d.umask),  # from world-readable login.defs
            _kv("Default expiration date", ua(d.expire)),
            _kv("Days after expiry login usable", ua(d.inactive)),
            _kv("Skeleton directory", ua(d.skel)),
            urwid.Divider(),
            urwid.Text(("dim", " Read-only — from /etc/default/useradd and "
                               "/etc/login.defs.")),
        ]
        if not readable:
            rows.append(urwid.Text(("dim", " /etc/default/useradd is root-only; "
                                          "run GeST as root to see its values.")))
        self._content.original_widget = urwid.LineBox(
            urwid.ListBox(urwid.SimpleListWalker(rows)),
            title="Defaults for New Users")
        self.app.refresh()

    async def _load_auth(self) -> None:
        providers = await self.app.run_blocking(auth.read_providers)
        lines = await self.app.run_blocking(auth.read_lines)
        rows: list[urwid.Widget] = [
            urwid.Text(("hint", " Back-ends that resolve accounts "
                               "(from /etc/nsswitch.conf)")),
            urwid.Divider(),
        ]
        for p in providers:
            state = ("ok", "configured") if p.configured else \
                    ("dim", "not configured")
            rows.append(urwid.Text([("field", f" {p.name:<20}"), state]))
        rows += [
            urwid.Divider(),
            urwid.Text([("field", " passwd:  "), lines.get("passwd", "—")], wrap="clip"),
            urwid.Text([("field", " group:   "), lines.get("group", "—")], wrap="clip"),
            urwid.Divider(),
            urwid.Text(("dim", " Read-only status. Configuring NIS/LDAP/SSSD/"
                               "Winbind isn't supported in GeST yet.")),
        ]
        self._content.original_widget = urwid.LineBox(
            urwid.ListBox(urwid.SimpleListWalker(rows)),
            title="Authentication settings")
        self.app.refresh()

    def _current(self) -> str | None:
        if self._view not in ("users", "groups") or not self._order:
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
        elif key in ("left", "right"):
            self._cycle(-1 if key == "left" else 1)
        elif key == "g":
            self._view = "groups" if self._view == "users" else "users"
            self._show_tab()
        elif self._view in ("users", "groups"):
            if key == "f" and self._view == "users":
                self._filter = _FILTERS[(_FILTERS.index(self._filter) + 1) % len(_FILTERS)]
                self._content.original_widget = self._list_box(self._view)
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
