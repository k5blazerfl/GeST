"""Users & Groups in urwid: a YaST-style tabbed, transactional admin screen.

Four tabs — Users, Groups, Defaults for New Users, Authentication — switched
with ←/→ (g toggles Users⇄Groups). Editing is transactional (YaST-style):
add/edit/delete/password/member actions are *staged*, shown in the list with
+/~/- markers and a pending-count line; nothing touches the system until OK
(F10) applies them all. Cancel (F9) discards, and leaving the Users/Groups
editing surface with staged changes prompts to save or discard. Defaults and
Authentication are read-only status views. Reads are unprivileged; the staged
operations replay through the polkit-gated UsersBackend on OK.
"""

from __future__ import annotations

import urwid

from gest.core.users import auth, commands, defaults, pending, reader
from gest.core.users.backend_client import UsersBackend
from gest.core.users.model import User
from gest.core.users.pending import PendingChanges
from gest.tui.runtime import App, Modal, Screen, accel_label

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


def _mark(m: str | None) -> str:
    return f"{m:<2}" if m else "  "


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
    _EDIT_TABS = ("users", "groups", "defaults")   # transactional editing surface

    def __init__(self, app: App) -> None:
        self._view = "users"
        self._filter = "local"   # default to real login accounts, not services
        self._loads = 0          # completed loads (for tests to await)
        self._pending = PendingChanges()
        self._defaults = defaults.NewUserDefaults()   # last-read new-user defaults
        self._users: dict[str, User] = {}
        self._order: list[str] = []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)

        self._tabbar = urwid.Text("")
        self._count = urwid.Text("")
        self._content = urwid.WidgetPlaceholder(self._list_box("users"))
        body = urwid.Pile([
            ("pack", urwid.AttrMap(self._tabbar, "menubar")),
            ("pack", urwid.Divider()),
            ("weight", 1, self._content),
            ("pack", self._count),
            ("pack", self._action_bar()),
        ])
        super().__init__(
            app, body, title="User and Group Administration",
            footer_keys=[
                ("←/→", "Tabs"), ("f", "Filter"), ("a", "Add"), ("e", "Edit"),
                ("d", "Delete"), ("p", "Passwd"), ("m", "Member"),
                ("g", "Usr/Grp"), ("F10", "OK"), ("F9", "Cancel"), ("Esc", "Back"),
            ],
            help_text=(
                "User and group administration, in four tabs (←/→ to switch;\n"
                "g toggles Users ⇄ Groups).\n\n"
                "Editing is transactional: add/edit/delete/password/member changes\n"
                "are staged, not applied immediately. Staged rows are marked\n"
                "  + add    ~ edit    - delete\n"
                "and counted below the list. F10 (OK) applies every staged change;\n"
                "F9 (Cancel) discards them. d on an already-staged row clears its\n"
                "staged change. Leaving Users/Groups with staged changes prompts\n"
                "to save or discard.\n\n"
                "On the Users tab, f cycles the filter: local human accounts →\n"
                "system/service accounts → all. Groups are always shown in full.\n\n"
                "Defaults for New Users — edit (e) the defaults applied to new\n"
                "accounts (group/shell/home prefix/inactive/expire); the change\n"
                "is staged and written via useradd -D on OK. Umask and skeleton\n"
                "are read-only. Authentication is a read-only status view\n"
                "(/etc/nsswitch.conf)."
            ),
        )
        self._render_tabs()
        self._refresh_count()
        app.run_async(self._load())

    # -- chrome -------------------------------------------------------------

    def _action_bar(self) -> urwid.Widget:
        return urwid.Columns([
            ("pack", accel_label("Help")),
            ("weight", 1, urwid.Text("")),
            ("pack", accel_label("Cancel")),
            ("pack", urwid.Text("  ")),
            ("pack", accel_label("OK")),
            ("pack", urwid.Text(" ")),
        ])

    def _render_tabs(self) -> None:
        parts: list = [" "]
        for i, (key, label) in enumerate(self._TABS):
            if i:
                parts.append(("dim", "  │  "))
            chip = f" {label} "
            parts.append(("menu_focus", chip) if key == self._view else chip)
        self._tabbar.set_text(parts)

    def _refresh_count(self) -> None:
        if self._pending.is_empty:
            self._count.set_text(("dim", " No pending changes"))
        else:
            self._count.set_text([
                ("ok", f" {len(self._pending)} pending change(s)"),
                ("dim", f"   {self._pending.summary()}   ·   F10 OK · F9 Cancel"),
            ])
        self.app.refresh()

    # -- tab switching (guarded) -------------------------------------------

    def _cycle(self, delta: int) -> None:
        keys = [k for k, _ in self._TABS]
        self._switch_to(keys[(keys.index(self._view) + delta) % len(keys)])

    def _switch_to(self, new_view: str) -> None:
        leaving_edit = (self._view in self._EDIT_TABS
                        and new_view not in self._EDIT_TABS)
        if leaving_edit and not self._pending.is_empty:
            self._guard(lambda: self._do_switch(new_view))
        else:
            self._do_switch(new_view)

    def _do_switch(self, new_view: str) -> None:
        self._view = new_view
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
            header = "  " + _fmt_user("Login", "UID", "Name", "Groups")
        else:
            title = "Groups"   # groups are always shown in full
            header = "  " + _fmt_group("Group", "GID", "Members")
        hdr = urwid.AttrMap(urwid.Text(header, wrap="clip"), "pane_title")
        inner = urwid.Pile([
            ("pack", hdr), ("pack", urwid.Divider("─")), ("weight", 1, self._list),
        ])
        return urwid.LineBox(inner, title=title)

    # -- loading (projects staged changes over live state) ------------------

    async def _load(self) -> None:
        prev = self._walker.focus if self._walker else 0
        if self._view == "users":
            rows, self._order = await self._user_rows()
        else:
            rows, self._order = await self._group_rows()
        empty = f" (no {self._filter} users)" if self._view == "users" else " (no groups)"
        self._walker[:] = rows or [urwid.Text(empty)]
        if self._order:
            self._walker.set_focus(min(prev, len(self._order) - 1))
        self._loads += 1
        self.app.refresh()

    async def _user_rows(self) -> tuple[list, list[str]]:
        users = await self.app.run_blocking(reader.list_users)
        groups = await self.app.run_blocking(reader.list_groups)
        users = [u for u in users if _passes(u.uid, self._filter)]
        gid_name = {g.gid: g.name for g in groups}
        self._users = {u.name: u for u in users}
        rows, order = [], []
        for u in users:
            mk = self._pending.user_marker(u.name)
            rows.append(_row(_mark(mk) + _fmt_user(
                u.name, str(u.uid), u.full_name,
                self._group_summary(u, gid_name, groups))))
            order.append(u.name)
        for op in self._pending.added_users():   # staged accounts not yet on disk
            if op.key not in self._users:
                d = op.data
                rows.append(_row(_mark("+") + _fmt_user(
                    d["name"], "—", d["comment"], d["groups"] or "—")))
                order.append(op.key)
        return rows, order

    async def _group_rows(self) -> tuple[list, list[str]]:
        groups = await self.app.run_blocking(reader.list_groups)
        live = {g.name for g in groups}
        rows, order = [], []
        for g in groups:
            mk = self._pending.group_marker(g.name)
            rows.append(_row(_mark(mk) + _fmt_group(
                g.name, str(g.gid), ", ".join(g.members))))
            order.append(g.name)
        for op in self._pending.added_groups():
            if op.key not in live:
                rows.append(_row(_mark("+") + _fmt_group(op.data["name"], "—", "")))
                order.append(op.key)
        return rows, order

    @staticmethod
    def _group_summary(user: User, gid_name: dict[int, str], groups: list) -> str:
        primary = gid_name.get(user.gid, str(user.gid))
        supp = reader.member_groups(user.name, groups)
        return ", ".join([primary, *[g for g in supp if g != primary]])

    async def _load_defaults(self) -> None:
        d = await self.app.run_blocking(defaults.read_defaults)
        groups = await self.app.run_blocking(reader.list_groups)
        readable = await self.app.run_blocking(defaults.useradd_readable)
        self._defaults = d
        staged = self._pending.defaults_op()
        sd = staged.data if staged else {}
        # /etc/default/useradd is typically root-only; show that honestly
        # rather than an empty value that reads as "unset".
        unread = "(requires root)"

        def field(label: str, key: str, current: str, editable: bool = True):
            if editable and sd.get(key):        # a staged override wins
                return urwid.Text([("field", f" {label:<32}"),
                                   ("ok", sd[key]), ("dim", "  (staged)")], wrap="clip")
            shown = current or (unread if (editable and not readable) else "—")
            return _kv(label, shown)

        group = d.group
        if group.isdigit() and not sd.get("group"):   # resolve gid → name for display
            gid_name = {str(g.gid): g.name for g in groups}
            group = f"{gid_name.get(group, group)} ({group})"
        rows = [
            urwid.Text(("hint", " Settings applied to newly-created users  "
                               "(e edit · staged, applied on OK)")),
            urwid.Divider(),
            field("Default group", "group", group),
            field("Default login shell", "shell", d.shell),
            field("Home directory prefix", "home", d.home),
            field("Umask for home directory", "umask", d.umask, editable=False),
            field("Default expiration date", "expire", d.expire),
            field("Days after expiry login usable", "inactive", d.inactive),
            _kv("Skeleton directory", d.skel or (unread if not readable else "—")),
            urwid.Divider(),
            urwid.Text(("dim", " Editable fields write via useradd -D. Umask and "
                               "skeleton are read-only (login.defs).")),
        ]
        if not readable:
            rows.append(urwid.Text(("dim", " /etc/default/useradd is root-only; "
                                          "current values need root to read.")))
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

    # -- staging + apply/discard --------------------------------------------

    def _after_stage(self) -> None:
        self._refresh_count()
        if self._view == "defaults":
            self.app.run_async(self._load_defaults())
        else:
            self.app.run_async(self._load())

    async def _apply(self) -> None:
        if self._pending.is_empty:
            self.app.notify("No pending changes to apply.", error=True)
            return
        backend = UsersBackend()
        try:
            await backend.connect()
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            return
        ok_n = fail_n = 0
        last_err = ""
        for op in self._pending.ordered():
            try:
                ok, out = await self._apply_op(backend, op)
            except Exception as exc:
                ok, out = False, str(exc)
            if ok:
                ok_n += 1
            else:
                fail_n += 1
                last_err = out or op.label
        await backend.close()
        self._pending.clear()
        self._refresh_count()
        if fail_n:
            self.app.notify(f"applied {ok_n}, {fail_n} failed — {last_err}", error=True)
        else:
            self.app.notify(f"applied {ok_n} change(s)")
        await self._load()

    @staticmethod
    async def _apply_op(b: UsersBackend, op: pending.Op):
        d, k = op.data, op.kind
        if k == pending.ADD_USER:
            return await b.add_user(d["name"], d["comment"], d["shell"], "",
                                    d["groups"], d["system"])
        if k == pending.MOD_USER:
            return await b.modify_user(d["name"], d["comment"], d["shell"], d["groups"])
        if k == pending.DEL_USER:
            return await b.delete_user(d["name"], d["remove_home"])
        if k == pending.SET_PASSWORD:
            return await b.set_password(d["name"], d["password"])
        if k == pending.ADD_GROUP:
            return await b.add_group(d["name"], d["system"])
        if k == pending.DEL_GROUP:
            return await b.delete_group(d["name"])
        if k == pending.SET_MEMBER:
            return await b.set_group_member(d["group"], d["user"], d["add"])
        if k == pending.SET_DEFAULTS:
            return await b.set_defaults(d.get("group", ""), d.get("home", ""),
                                        d.get("shell", ""), d.get("inactive", ""),
                                        d.get("expire", ""))
        return False, f"unknown op {k}"

    def _discard(self) -> None:
        if self._pending.is_empty:
            self.app.notify("No pending changes.")
            return

        def do():
            self.app.pop()
            self._pending.clear()
            self._refresh_count()
            self.app.notify("discarded pending changes")
            self.app.run_async(self._load())

        modal = Modal(self.app, f"Discard {len(self._pending)} pending change(s)?",
                      [], [("Discard", do), ("Keep editing", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 55), height=("relative", 35))

    def _guard(self, proceed) -> None:
        """Prompt to save/discard staged changes before leaving; else proceed."""
        if self._pending.is_empty:
            proceed()
            return

        async def save_then():
            await self._apply()
            proceed()

        def save():
            self.app.pop()
            self.app.run_async(save_then())

        def discard():
            self.app.pop()
            self._pending.clear()
            self._refresh_count()
            proceed()

        modal = Modal(
            self.app, f"{len(self._pending)} pending change(s)",
            [urwid.Text("Save them, discard them, or keep editing?")],
            [("Save", save), ("Discard", discard), ("Keep editing", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 55), height=("relative", 40))

    # -- key handling -------------------------------------------------------

    def handle_key(self, key):
        if key == "esc":
            self._guard(self.app.pop)
        elif key in ("left", "right"):
            self._cycle(-1 if key == "left" else 1)
        elif key == "g":
            self._switch_to("groups" if self._view == "users" else "users")
        elif key == "f10":
            self.app.run_async(self._apply())
        elif key == "f9":
            self._discard()
        elif self._view == "defaults":
            if key in ("e", "enter"):
                self._edit_defaults()
            elif key == "d" and self._pending.defaults_op() is not None:
                self._pending.remove_for_defaults()
                self._after_stage()
                self.app.notify("cleared staged defaults")
            else:
                return key
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

    # -- forms (all stage; none apply immediately) --------------------------

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
                self._pending.stage(pending.add_group_op(n, system.state))
                self._after_stage()

            self._open("Add group", [name, system], save)
            return
        self._user_form("Add user", "",
                        {"comment": "", "shell": "/bin/bash", "groups": "", "system": False},
                        is_add=True, new=True)

    def _edit(self) -> None:
        if self._view == "groups":
            self.app.notify("Edit membership with m; renaming groups isn't supported.",
                            error=True)
            return
        name = self._current()
        if not name:
            return
        add_op = self._pending.added_user(name)
        if add_op is not None:   # editing a still-staged new account
            self._user_form(f"Edit staged user: {name}", name, add_op.data, is_add=True)
        elif name in self._users:
            u = self._users[name]
            data = {"comment": u.full_name, "shell": u.shell,
                    "groups": ",".join(reader.groups_for(name)), "system": False}
            self._user_form(f"Edit user: {name}", name, data, is_add=False)

    def _user_form(self, title: str, name: str, data: dict,
                   *, is_add: bool, new: bool = False) -> None:
        name_edit = urwid.Edit("Login name: ", name)
        comment = urwid.Edit("Full name: ", data.get("comment", ""))
        shell = urwid.Edit("Shell: ", data.get("shell") or "/bin/bash")
        groups = urwid.Edit("Extra groups: ", data.get("groups", ""))
        system = urwid.CheckBox("System account", state=data.get("system", False))
        rows: list = [name_edit if new else urwid.Text(("field", f" Login name: {name}"))]
        rows += [comment, shell, groups]
        if is_add:
            rows.append(system)

        def save():
            n = name_edit.edit_text.strip() if new else name
            if not n:
                self.app.notify("A login name is required.", error=True)
                return
            self.app.pop()
            if is_add:
                self._pending.stage(pending.add_user_op(
                    n, comment.edit_text.strip(), shell.edit_text.strip(),
                    groups.edit_text.strip(), system.state))
            else:
                self._pending.stage(pending.mod_user_op(
                    n, comment.edit_text.strip(), shell.edit_text.strip(),
                    groups.edit_text.strip()))
            self._after_stage()

        self._open(title, rows, save)

    def _delete(self) -> None:
        name = self._current()
        if not name:
            return
        if self._view == "users":
            if self._pending.user_marker(name):   # already staged → undo it
                self._pending.remove_for_user(name)
                self._after_stage()
                self.app.notify(f"cleared staged changes for {name}")
                return
            rmhome = urwid.CheckBox("Also remove home directory")

            def do():
                self.app.pop()
                self._pending.stage(pending.del_user_op(name, rmhome.state))
                self._after_stage()

            self._confirm(f"Stage deletion of user “{name}”?", [rmhome], do)
        else:
            if self._pending.group_marker(name):
                self._pending.remove_for_group(name)
                self._after_stage()
                self.app.notify(f"cleared staged changes for {name}")
                return

            def do():
                self.app.pop()
                self._pending.stage(pending.del_group_op(name))
                self._after_stage()

            self._confirm(f"Stage deletion of group “{name}”?", [], do)

    def _edit_defaults(self) -> None:
        staged = self._pending.defaults_op()
        src = staged.data if staged else {}
        d = self._defaults

        def pre(key: str, current: str) -> str:
            return src.get(key) or current

        group = urwid.Edit("Default group: ", pre("group", d.group))
        shell = urwid.Edit("Login shell: ", pre("shell", d.shell))
        home = urwid.Edit("Home prefix: ", pre("home", d.home))
        inactive = urwid.Edit("Inactive days: ", pre("inactive", d.inactive))
        expire = urwid.Edit("Expire (YYYY-MM-DD): ", pre("expire", d.expire))
        fields = [("group", group), ("home", home), ("shell", shell),
                  ("inactive", inactive), ("expire", expire)]

        def save():
            data = {k: w.edit_text.strip() for k, w in fields if w.edit_text.strip()}
            if not data:
                self.app.notify("Nothing to change.", error=True)
                return
            try:   # validate now for immediate feedback
                commands.useradd_defaults_argv(**data)
            except ValueError as exc:
                self.app.notify(str(exc), error=True)
                return
            self.app.pop()
            self._pending.stage(pending.set_defaults_op(data))
            self._after_stage()

        rows = [urwid.Text(("hint", "Blank = leave unchanged. Applied on OK.")),
                urwid.Divider(), group, home, shell, inactive, expire]
        self._open("Edit defaults for new users", rows, save)

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
            self.app.pop()
            self._pending.stage(pending.set_password_op(name, pw.edit_text))
            self._after_stage()

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
            self._pending.stage(pending.set_member_op(group, u, add))
            self._after_stage()

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
        modal = Modal(self.app, message, rows, [("Stage", do), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 60), height=("relative", 45))
