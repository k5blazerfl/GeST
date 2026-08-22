"""The GeSI install wizard — a YaST-style gated passage (urwid).

A left step-rail and a Back/Next flow replace the old flat settings dump. Each
gate owns a slice of a shared, mutable :class:`InstallSelections`; the System
Role gate proposes a coherent whole so later gates edit real defaults, not blank
fields. The terminus is the settings overview (:class:`InstallOverviewScreen`),
which stays the review + install surface. The engine/plan/run path is unchanged.

    Localization → Get Online → System Role → Disk → Base System → Your Account
      → Review (overview) → Install

``gest --install`` calls :func:`start` to launch straight into the first gate.
"""

from __future__ import annotations

import os

import urwid

from gest.core.disk import provision
from gest.core.disk import reader as disk_reader
from gest.core.install import assemble, capabilities
from gest.core.install.assemble import InstallSelections
from gest.core.install.netcheck import check_connectivity
from gest.core.install.plan import ADMIN_MODELS, LICENSE_POLICIES, sets_root_password
from gest.core.system import console as console_core
from gest.core.system import hostname as hostname_core
from gest.core.system import locale as locale_core
from gest.core.system import timezone as timezone_core
from gest.core.users.commands import valid_name as valid_user_name
from gest.tui.runtime import App, Modal, NavPile, Screen, boxed, focusable_actions

# The rail: ordered (key, title). "review" is the terminus (the overview screen).
_RAIL: tuple[tuple[str, str], ...] = (
    ("localization", "Localization"),
    ("online", "Get Online"),
    ("role", "System Role"),
    ("disk", "Disk"),
    ("base", "Base System"),
    ("account", "Your Account"),
    ("review", "Review"),
)
_RAIL_KEYS = [k for k, _ in _RAIL]

_LICENSE_LABELS = {
    "libre": "Libre — free/open licenses only (@FREE)",
    "redistributable": "Redistributable — firmware + NVIDIA driver, no EULAs",
    "full": "Full — everything, including click-through EULAs",
}
_ADMIN_LABELS = {
    "traditional": "Traditional — root password, escalate with su",
    "sudo-augmented": "Sudo-augmented — root password AND wheel sudo",
    "rootless": "Rootless — root locked, wheel user escalates (Ubuntu-style)",
}


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


def _detect_ram_bytes() -> int:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError):
        return 8 * 1024 ** 3


def _rail_widget(current: str) -> urwid.Widget:
    rows = []
    cur_i = _RAIL_KEYS.index(current)
    for i, (_key, title) in enumerate(_RAIL):
        if i == cur_i:
            rows.append(urwid.Text(("title", f" ▶ {title}")))
        elif i < cur_i:
            rows.append(urwid.Text(("ok", f" ✓ {title}")))
        else:
            rows.append(urwid.Text(("dim", f"   {title}")))
    # Filler makes the rail a BOX widget so it sits in a Columns beside the
    # (box) settings list without a flow/box sizing mismatch.
    return boxed(urwid.Filler(urwid.Pile(rows), valign="top"), title="Install")


def _choice_modal(app: App, title: str, options: list[tuple[str, str]],
                  current: str, apply, done) -> None:
    """A small single-choice picker: ``options`` are (key, label) rows; Enter (or
    Select) applies the focused key. Used for role/license/admin/build choices."""
    walker = urwid.SimpleFocusListWalker([_row(label) for _key, label in options])
    keys = [k for k, _ in options]
    if current in keys:
        walker.set_focus(keys.index(current))

    def select(_w=None):
        pos = walker.get_focus()[1]
        if pos is not None:
            apply(keys[pos])
            app.pop()
            done()

    body = urwid.BoxAdapter(urwid.ListBox(walker), min(len(options) + 1, 8))
    modal = Modal(app, title, [body], [("Select", select), ("Cancel", app.pop)])
    app.push_modal(modal, width=("relative", 66), height=("relative", 50))


def _pick_modal(app: App, title: str, choices: list[str], current: str,
                apply, done) -> None:
    """A filterable long-list picker (timezones/locales/keymaps)."""
    walker = urwid.SimpleFocusListWalker([])
    visible = list(choices)

    def fill(items):
        nonlocal visible
        visible = items
        walker[:] = [_row(c) for c in items] or [urwid.Text(" (no matches)")]
        if items and current in items:
            walker.set_focus(items.index(current))
        elif items:
            walker.set_focus(0)

    filt = urwid.Edit("Filter: ")
    urwid.connect_signal(
        filt, "change",
        lambda _e, text: fill([c for c in choices if text.strip().lower() in c.lower()]))
    fill(choices)

    def select(_w=None):
        if visible and walker.focus is not None:
            apply(visible[walker.get_focus()[1]])
            app.pop()
            done()

    body = urwid.Pile([
        ("pack", urwid.Text(("hint", "Type to filter · ↓ into the list · Select."))),
        ("pack", filt),
        ("pack", urwid.Divider()),
        ("weight", 1, urwid.BoxAdapter(urwid.ListBox(walker), 10)),
    ])
    modal = Modal(app, title, [body], [("Select", select), ("Cancel", app.pop)])
    app.push_modal(modal, width=("relative", 62), height=("relative", 74))


class WizardStep(Screen):
    """Base gate: left rail + a right list of editable rows, ending in Continue.

    Subclasses implement :meth:`setting_rows` (``(label, value, action)`` tuples, or
    ``None`` for a divider) and may override :meth:`validate` (return a blocker
    string to refuse Continue) and :meth:`help`. Enter edits the focused row or,
    on the Continue row, advances; Esc backs out (pops to the previous gate, or
    the menu at the first gate).
    """

    step_key = ""
    step_title = ""

    def __init__(self, app: App, sel: InstallSelections, *, return_to=None) -> None:
        self.sel = sel
        # When set (a Screen factory), Continue returns here instead of advancing
        # the rail — used by the Review gate's jump-back so editing one setting
        # drops straight back to Review rather than walking the rest of the rail.
        self._return_to = return_to
        self._walker = urwid.SimpleFocusListWalker([])
        self._list = urwid.ListBox(self._walker)
        cols = urwid.Columns(
            [(20, _rail_widget(self.step_key)),
             boxed(self._list, title=self.step_title)],
            dividechars=1, focus_column=1)
        # Continue is a right-aligned action button at the bottom (GeST's
        # ActionRow convention), not an in-list row — Tab reaches it, Enter fires.
        self._continue_row = focusable_actions([("Continue", self.advance)])
        body = NavPile([("weight", 1, cols), ("pack", self._continue_row)])
        super().__init__(
            app, body, title=f"Install Gentoo — {self.step_title}",
            footer_keys=[("Enter", "Select / Edit"), ("Tab", "Continue"),
                         ("Esc", "Back")],
            help_text=self.help())
        self.configure_pane_cycle(body, [0], action_row=self._continue_row)
        self._render()

    # -- subclass hooks --------------------------------------------------------
    def setting_rows(self) -> list:
        return []

    def validate(self) -> str | None:
        return None

    def help(self) -> str:
        return ""

    # -- rendering + navigation ------------------------------------------------
    def _render(self) -> None:
        items: list[urwid.Widget] = []
        self._actions: list = []
        for entry in self.setting_rows():
            if entry is None:
                items.append(urwid.Divider())
                self._actions.append(None)
                continue
            label, value, action = entry
            text = label if value is None else f"{label:<24}: {value}"
            items.append(_row(text))
            self._actions.append(action)
        self._walker[:] = items
        self._focus_first()

    def _selectable_positions(self) -> list[int]:
        return [i for i, a in enumerate(self._actions) if a is not None]

    def _focus_first(self) -> None:
        sel = self._selectable_positions()
        if sel:
            self._walker.set_focus(sel[0])

    def handle_key(self, key):
        # Only drive the settings list here; the Continue button (action row) is
        # reached by Tab and fired by the base nav (Enter/Space).
        if self._on_action_row():
            return key
        if key in ("up", "down"):
            sel = self._selectable_positions()
            if not sel:
                return None
            pos = self._walker.get_focus()[1]
            cur = sel.index(pos) if pos in sel else 0
            nxt = min(len(sel) - 1, cur + 1) if key == "down" else max(0, cur - 1)
            self._walker.set_focus(sel[nxt])
            return None
        if key == "enter":
            pos = self._walker.get_focus()[1]
            action = self._actions[pos] if 0 <= pos < len(self._actions) else None
            if callable(action):
                action()
            return None
        return key

    def advance(self) -> None:
        """Validate this gate and push the next one (public for tests)."""
        msg = self.validate()
        if msg:
            self.app.notify(msg, error=True)
            return
        self.app.push(self._return_to() if self._return_to else self._next_screen())

    def _next_screen(self) -> Screen:
        nxt = _RAIL_KEYS[_RAIL_KEYS.index(self.step_key) + 1]
        return make_step(nxt, self.app, self.sel)


# --- gates -------------------------------------------------------------------

class LocalizationStep(WizardStep):
    step_key = "localization"
    step_title = "Localization"

    def help(self) -> str:
        return ("Set the target's timezone, locale and console keymap. These are\n"
                "offline pickers — no network needed.")

    def setting_rows(self):
        return [
            ("Timezone", self.sel.timezone, self._edit_timezone),
            ("Locale", self.sel.locale, self._edit_locale),
            ("Console keymap", self.sel.keymap, self._edit_keymap),
        ]

    def _edit_timezone(self):
        _pick_modal(self.app, "Timezone", timezone_core.list_zones(),
                    self.sel.timezone, self._set("timezone"), self._render)

    def _edit_locale(self):
        _pick_modal(self.app, "Locale", locale_core.list_locales(),
                    self.sel.locale, self._set("locale"), self._render)

    def _edit_keymap(self):
        _pick_modal(self.app, "Console keymap", console_core.list_keymaps(),
                    self.sel.keymap, self._set("keymap"), self._render)

    def _set(self, attr):
        def apply(value):
            setattr(self.sel, attr, value)
        return apply


class OnlineStep(WizardStep):
    step_key = "online"
    step_title = "Get Online"

    def help(self) -> str:
        return ("The installer downloads a stage3 and syncs Portage, so the live\n"
                "environment needs a working network connection before you continue.\n"
                "Wired usually comes up automatically; for Wi-Fi use Network → Wi-Fi\n"
                "from the main menu (Esc), then re-check here.")

    def _online(self) -> bool:
        ok, _detail = check_connectivity()      # (bool, detail) — network probe
        return ok

    def setting_rows(self):
        online = self._online()
        return [
            ("Network", "connected" if online else "NOT connected — required", None),
            None,
            ("Bring up wired network (dhcpcd)", None, self._dhcp),
            ("Re-check connectivity", None, self._render),
        ]

    def _dhcp(self):
        self.app.notify("Bringing up wired network (dhcpcd) …")
        self.app.run_async(self._run_dhcp())

    async def _run_dhcp(self):
        import contextlib

        from gest.core.exec.select import choose_executor
        with contextlib.suppress(Exception):
            await choose_executor().run(["dhcpcd"])
        self._render()

    def validate(self):
        return None if self._online() else \
            "No network — the install needs a connection to fetch the stage3."


class RoleStep(WizardStep):
    step_key = "role"
    step_title = "System Role"

    _ROLES = (
        ("desktop", "Desktop (HeDE)  — full graphical desktop, rootless sudo"),
        ("server", "Server          — headless, sshd + firewall, root + su"),
        ("minimal", "Minimal         — base Gentoo from source, no desktop"),
        ("custom", "Custom          — the Desktop baseline, everything editable"),
    )

    def help(self) -> str:
        return ("Pick what this machine is for. The role proposes a coherent set of\n"
                "defaults (build strategy, licenses, admin model, services) that the\n"
                "later gates then let you fine-tune.")

    def setting_rows(self):
        out = [("Selected role", self.sel.role, None), None]
        for key, label in self._ROLES:
            mark = "◉" if key == self.sel.role else "○"
            out.append((f"{mark} {label}", None, self._choose(key)))
        return out

    def _choose(self, role):
        def apply():
            assemble.apply_role(self.sel, role)
            self._render()
            self.app.notify(f"role: {role}")
        return apply


class DiskStep(WizardStep):
    step_key = "disk"
    step_title = "Disk"

    def help(self) -> str:
        return ("Choose the target disk. A guided layout is proposed (ESP + RAM-sized\n"
                "swap + root); you can adjust the sizes and root filesystem. The disk\n"
                "is only wiped after you confirm at the Review step — nothing yet.")

    def setting_rows(self):
        disks = [d for d in disk_reader.list_block_devices() if d.type == "disk"]
        summary = self._layout_summary()
        return [
            ("Target disk", self.sel.disk or "(none — required)", lambda: self._pick_disk(disks)),
            None,
            ("Proposed layout", summary, None),
            ("ESP size", self.sel.esp_size, self._edit_esp),
            ("Swap size", self.sel.swap_size or "(none)", self._edit_swap),
            ("Root filesystem", self.sel.root_fs, self._edit_root_fs),
        ]

    def _layout_summary(self) -> str:
        if not self.sel.disk:
            return "(pick a disk)"
        esp = "" if self.sel.firmware == "bios" else f"ESP {self.sel.esp_size} + "
        swap = f"swap {self.sel.swap_size} + " if self.sel.swap_size else ""
        return f"{esp}{swap}root ({self.sel.root_fs}, rest)"

    def _pick_disk(self, disks):
        opts = [(d.name, f"{d.name}  {getattr(d, 'size', '')}") for d in disks] \
            or [("", "(no disks detected)")]
        _choice_modal(self.app, "Target disk", opts, self.sel.disk,
                      self._on_disk, self._render)

    def _on_disk(self, name):
        self.sel.disk = name
        if name:
            # guided sizing: 1G ESP, RAM-sized swap (propose_layout's rule)
            self.sel.esp_size = provision.ESP_PROPOSAL_SIZE
            self.sel.swap_size = provision.propose_swap_size(_detect_ram_bytes())

    def _edit_esp(self):
        self._edit_text("ESP size", "esp_size")

    def _edit_swap(self):
        self._edit_text("Swap size (blank = none)", "swap_size")

    def _edit_root_fs(self):
        from gest.core.disk.commands import ROOT_FS_KINDS
        opts = [(fs, fs) for fs in sorted(ROOT_FS_KINDS)]
        _choice_modal(self.app, "Root filesystem", opts, self.sel.root_fs,
                      self._set_attr("root_fs"), self._render)

    def _edit_text(self, title, attr):
        edit = urwid.Edit(f"{title}: ", getattr(self.sel, attr))

        def save():
            setattr(self.sel, attr, edit.edit_text.strip())
            self.app.pop()
            self._render()
        modal = Modal(self.app, title, [edit], [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 60))

    def _set_attr(self, attr):
        def apply(value):
            setattr(self.sel, attr, value)
        return apply

    def validate(self):
        return None if self.sel.disk else "Select a target disk."


class BaseSystemStep(WizardStep):
    step_key = "base"
    step_title = "Base System"

    def help(self) -> str:
        return ("How the base system is built and licensed. Binary packages are fast;\n"
                "compiling from source tunes to your CPU. The license rung sets\n"
                "ACCEPT_LICENSE; Features become system-wide USE flags. Your role has\n"
                "proposed sensible values — change any of them or just continue.")

    def setting_rows(self):
        build = "Binary packages (fast)" if self.sel.binary_pref else "Compile from source"
        feats = ", ".join(sorted(self.sel.capabilities)) or "(none)"
        return [
            ("Build strategy", build, self._edit_build),
            ("License policy", _LICENSE_LABELS[self.sel.license], self._edit_license),
            ("Features (USE)", feats, self._edit_features),
        ]

    def _edit_build(self):
        opts = [("binary", "Binary packages — prebuilt, fast, modest hardware"),
                ("source", "Compile from source — tuned to your CPU, long build")]
        cur = "binary" if self.sel.binary_pref else "source"
        _choice_modal(self.app, "Build strategy", opts, cur,
                      lambda k: setattr(self.sel, "binary_pref", k == "binary"),
                      self._render)

    def _edit_license(self):
        opts = [(k, _LICENSE_LABELS[k]) for k in ("libre", "redistributable", "full")]
        _choice_modal(self.app, "License policy", opts, self.sel.license,
                      lambda k: setattr(self.sel, "license", k), self._render)

    def _edit_features(self):
        boxes = [urwid.CheckBox(cap.label, state=cap.key in self.sel.capabilities)
                 for cap in capabilities.CAPABILITIES]

        def save():
            self.sel.capabilities = {
                cap.key for cap, box in zip(capabilities.CAPABILITIES, boxes, strict=True)
                if box.state}
            self.app.pop()
            self._render()
        modal = Modal(self.app, "Features (system-wide USE)",
                      [urwid.Text(("hint", "Checked = enable the feature everywhere.")),
                       urwid.Divider(), *boxes],
                      [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 60), height=("relative", 70))

    def validate(self):
        if self.sel.license not in LICENSE_POLICIES:
            return f"Unknown license policy: {self.sel.license}"
        return None


class AccountStep(WizardStep):
    step_key = "account"
    step_title = "Your Account"

    def help(self) -> str:
        return ("The machine's hostname, admin model, and accounts. Rootless locks\n"
                "the root account and needs an admin (wheel) user; the other models\n"
                "set a root password. Your role proposed a default admin model.")

    def setting_rows(self):
        user = self.sel.user_name if self.sel.create_user else "(none)"
        rootpw = "(set)" if self.sel.root_password else "(not set)"
        out = [
            ("Hostname", self.sel.hostname, self._edit_hostname),
            ("Admin model", _ADMIN_LABELS[self.sel.admin_model], self._edit_admin),
        ]
        if self.sel.admin_model in ("sudo-augmented", "rootless"):
            out.append(("Escalator", self.sel.escalator, self._edit_escalator))
        out.append(("User account", user, self._edit_user))
        if sets_root_password(self.sel.admin_model):
            out.append(("Root password", rootpw, self._edit_rootpw))
        return out

    def _edit_hostname(self):
        self._edit_text("Hostname", "hostname")

    def _edit_admin(self):
        opts = [(k, _ADMIN_LABELS[k]) for k in ADMIN_MODELS]
        _choice_modal(self.app, "Admin model", opts, self.sel.admin_model,
                      lambda k: setattr(self.sel, "admin_model", k), self._render)

    def _edit_escalator(self):
        _choice_modal(self.app, "Escalator", [("sudo", "sudo"), ("doas", "doas")],
                      self.sel.escalator,
                      lambda k: setattr(self.sel, "escalator", k), self._render)

    def _edit_user(self):
        create = urwid.CheckBox("Create a user", state=self.sel.create_user)
        name = urwid.Edit("Name              : ", self.sel.user_name)
        comment = urwid.Edit("Full name/comment : ", self.sel.user_comment)
        wheel = urwid.CheckBox("Admin (wheel) user", state=self.sel.user_wheel)

        def save():
            if create.state:
                uname = name.edit_text.strip()
                if not valid_user_name(uname):
                    self.app.notify("Invalid user name.", error=True)
                    return
                self.sel.create_user = True
                self.sel.user_name = uname
                self.sel.user_comment = comment.edit_text.strip()
                self.sel.user_wheel = wheel.state
            else:
                self.sel.create_user = False
            self.app.pop()
            self._render()
        modal = Modal(self.app, "User account",
                      [urwid.Text(("hint", "An admin user (wheel) for day-to-day use.")),
                       urwid.Divider(), create, name, comment, wheel],
                      [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 70), height=("relative", 60))

    def _edit_rootpw(self):
        pw = urwid.Edit("Root password: ", mask="*")
        pw2 = urwid.Edit("Confirm      : ", mask="*")

        def save():
            if pw.edit_text != pw2.edit_text:
                self.app.notify("Passwords do not match.", error=True)
                return
            if not pw.edit_text:
                self.app.notify("Empty password.", error=True)
                return
            self.sel.root_password = pw.edit_text
            self.app.pop()
            self._render()
        modal = Modal(self.app, "Root password", [pw, pw2],
                      [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 60))

    def _edit_text(self, title, attr):
        edit = urwid.Edit(f"{title}: ", getattr(self.sel, attr))

        def save():
            setattr(self.sel, attr, edit.edit_text.strip())
            self.app.pop()
            self._render()
        modal = Modal(self.app, title, [edit], [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 60))

    def validate(self):
        if not hostname_core.valid_hostname(self.sel.hostname):
            return f"Invalid hostname: {self.sel.hostname!r}"
        if sets_root_password(self.sel.admin_model):
            if not self.sel.root_password:
                return "Set a root password (or choose the Rootless admin model)."
        elif not (self.sel.create_user and valid_user_name(self.sel.user_name)
                  and self.sel.user_wheel):
            return "Rootless needs an admin (wheel) user — create one."
        return None


_STEPS = {
    "localization": LocalizationStep,
    "online": OnlineStep,
    "role": RoleStep,
    "disk": DiskStep,
    "base": BaseSystemStep,
    "account": AccountStep,
}


def make_step(key: str, app: App, sel: InstallSelections, *, return_to=None) -> Screen:
    """Construct the gate for ``key`` (``"review"`` → the jump-back Review gate)."""
    if key == "review":
        from gest.tui.screens.install.review import ReviewScreen
        return ReviewScreen(app, sel)
    return _STEPS[key](app, sel, return_to=return_to)


def start(app: App) -> Screen:
    """The wizard's first gate, seeded with the Desktop proposal. ``gest --install``
    pushes this; the admin menu sits beneath it as an escape hatch."""
    return LocalizationStep(app, assemble.propose("desktop"))
