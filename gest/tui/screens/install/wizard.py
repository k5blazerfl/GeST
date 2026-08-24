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

from gest.core.datetime import reader as dt_reader
from gest.core.disk import provision
from gest.core.disk import reader as disk_reader
from gest.core.install import assemble, capabilities
from gest.core.install.assemble import InstallSelections, UserDraft
from gest.core.install.netcheck import check_connectivity
from gest.core.install.plan import ADMIN_MODELS, LICENSE_POLICIES, sets_root_password
from gest.core.network import reader as net_reader
from gest.core.system import console as console_core
from gest.core.system import hostname as hostname_core
from gest.core.system import locale as locale_core
from gest.core.system import timezone as timezone_core
from gest.core.users.commands import valid_name as valid_user_name
from gest.tui.runtime import App, Modal, NavPile, Screen, boxed, focusable_actions

# The installer's own ASCII wordmark — the GeST mark (screens/loading.py) with the
# trailing T turned into an I (a bottom bar added to the stem) so it reads GESI,
# "Gentoo System Installer". Kept LOCAL so the app-wide GeST loading logo is
# unchanged; same blue-over-purple split.
_GESI_LOGO_LINES = [
    "      ::::::::  :::::::::: :::::::: :::::::::::",
    "    :+:    :+: :+:       :+:    :+:    :+:",
    "   +:+        +:+       +:+           +:+",
    "  :#:        +#++:++#  +#++:++#++    +#+",
    " +#+   +#+# +#+              +#+    +#+",
    "#+#    #+# #+#       #+#    #+#    #+#",
    "########  ########## ########     ###########",
]
_GESI_LOGO_W = max(len(line) for line in _GESI_LOGO_LINES)
_GESI_LOGO_MARKUP = [
    ("box_title", "\n".join(_GESI_LOGO_LINES[:3]) + "\n"),   # top 3: Gentoo blue
    ("title", "\n".join(_GESI_LOGO_LINES[3:])),              # bottom 4: Gentoo purple
]

# The rail: ordered (key, title). "review" is the terminus (the overview screen).
_RAIL: tuple[tuple[str, str], ...] = (
    ("localization", "Welcome"),
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
    "sudo-augmented": "Sudo-augmented — root password, plus admins can use sudo",
    "rootless": "Rootless — no root login; an admin account uses sudo/doas",
}
_CLOCK_LABELS = {
    "chrony": "Network — uses Chrony to keep time in sync over the internet (NTP)",
    "local": "Local — set from this clock, no network sync",
}


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


class _PickList(urwid.ListBox):
    """A modal picker list where the highlight is a *staged* selection, not an
    action: arrow keys move it, and Enter advances to the Accept button
    (``on_enter``) rather than committing and closing. Nothing is applied until
    you accept — the same Back/Continue gating the wizard uses everywhere else.
    ``on_enter`` is wired to the owning modal's ``focus_buttons`` after it's built."""

    on_enter = None

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if key == "enter" and self.on_enter is not None:
            self.on_enter()
            return None
        return key


def _detect_ram_bytes() -> int:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError):
        return 8 * 1024 ** 3


_SIZE_UNITS = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4, "P": 1024 ** 5}


def _size_to_bytes(text: str) -> int:
    """Parse an lsblk human size ("238.5G", "512M", "1.8T") to bytes; 0 if unknown.

    lsblk's SIZE is 1024-based (a "G" is a GiB), matching :data:`_SIZE_UNITS`.
    """
    text = (text or "").strip().upper().rstrip("B")
    if not text:
        return 0
    if text[-1] in _SIZE_UNITS:
        try:
            return int(float(text[:-1]) * _SIZE_UNITS[text[-1]])
        except ValueError:
            return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


# Mount point + one-line purpose per partition label (the labels uefi_plan /
# bios_plan stamp onto each Partition). Drives the on-screen layout breakdown so
# it reads like the Gentoo Handbook's partition table.
_PART_PURPOSE = {
    "ESP": ("/boot/efi", "bootloader + kernels"),
    "BIOS": ("(raw)", "GRUB boot code"),
    "swap": ("swap", "paging + hibernate"),
    "root": ("/", "the whole system"),
    "home": ("/home", "your files, separate"),
}


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
    """A small single-choice picker, gated: arrow to a row to *stage* it, then
    Accept commits it (Enter on the list advances to Accept, it doesn't fire).
    Tab/Shift-Tab cycle the list and the Accept/Cancel buttons. The active choice
    keeps a filled ``◉`` (the rest ``○``) so the current value stays visible even
    without the focus highlight — e.g. the plain framebuffer console (nomodeset)."""
    keys = [k for k, _ in options]
    walker = urwid.SimpleFocusListWalker(
        [_row(("◉ " if k == current else "○ ") + lbl) for k, lbl in options])
    if current in keys:
        walker.set_focus(keys.index(current))

    def accept(_w=None):
        pos = walker.get_focus()[1]
        if pos is not None:
            apply(keys[pos])
            app.pop()
            done()

    listbox = _PickList(walker)
    body = urwid.BoxAdapter(listbox, min(len(options) + 1, 8))
    modal = Modal(app, title, [body], [("Accept", accept), ("Cancel", app.pop)])
    listbox.on_enter = modal.focus_buttons
    app.push_modal(modal, width=("relative", 66), height=("relative", 50))


def _pick_modal(app: App, title: str, choices: list[str], current: str,
                apply, done) -> None:
    """A filterable long-list picker (timezones/locales/keymaps)."""
    walker = urwid.SimpleFocusListWalker([])
    visible = list(choices)

    def fill(items):
        nonlocal visible
        visible = items
        # A ▸ marks the current value; others get a matching indent so the column
        # stays aligned (visible without relying on the focus highlight).
        walker[:] = [_row(("▸ " if c == current else "  ") + c) for c in items] \
            or [urwid.Text(" (no matches)")]
        if items and current in items:
            walker.set_focus(items.index(current))
        elif items:
            walker.set_focus(0)

    filt = urwid.Edit("Filter: ")
    urwid.connect_signal(
        filt, "change",
        lambda _e, text: fill([c for c in choices if text.strip().lower() in c.lower()]))
    fill(choices)

    def accept(_w=None):
        if visible and walker.focus is not None:
            apply(visible[walker.get_focus()[1]])
            app.pop()
            done()

    listbox = _PickList(walker)
    # Rows are top-level modal rows (not wrapped in one Pile) so Tab/Shift-Tab stop
    # on the search field, the list, and the buttons in turn — not "body ↔ buttons".
    rows = [
        urwid.Text(("hint", "Type to filter · Tab or ↓ to the list · Accept to apply.")),
        filt,
        urwid.Divider(),
        urwid.BoxAdapter(listbox, 10),
    ]
    modal = Modal(app, title, rows, [("Accept", accept), ("Cancel", app.pop)])
    listbox.on_enter = modal.focus_buttons
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
    # Top-bar header text. None → the default "Install Gentoo — {step_title}"; a
    # gate may set "" to show no header (the Welcome cover page does this so the
    # art stands alone).
    header_title: str | None = None

    def __init__(self, app: App, sel: InstallSelections, *, return_to=None,
                 exit_to_terminal: bool = False) -> None:
        self.sel = sel
        # When set (a Screen factory), Continue returns here instead of advancing
        # the rail — used by the Review gate's jump-back so editing one setting
        # drops straight back to Review rather than walking the rest of the rail.
        self._return_to = return_to
        self._walker = urwid.SimpleFocusListWalker([])
        self._list = urwid.ListBox(self._walker)
        # The detail panel — the bottom 40% of the right pane (see _compose_body).
        # It shows rich, per-row context for whatever setting is focused above,
        # refreshed on every focus change via the walker's focus callback.
        self._detail_text = urwid.Text("")
        self._row_meta: list = []
        self._walker.set_focus_changed_callback(self._sync_detail)
        # Back + Continue are right-aligned action buttons at the bottom (GeST's
        # ActionRow convention), not in-list rows — Tab reaches them, Enter fires.
        # At the root Welcome gate (exit_to_terminal), "Back" becomes "Exit to
        # Terminal" and quits the installer to the shell instead of popping; Esc
        # matches the button either way.
        self._exit_to_terminal = exit_to_terminal
        back_label, back_cb = (("Exit to Terminal", self.app_quit) if exit_to_terminal
                               else ("Back", self._back))
        self._nav_row = focusable_actions([(back_label, back_cb), ("Continue", self.advance)])
        body, cycle_container, cycle_positions = self._compose_body()
        header = (self.header_title if self.header_title is not None
                  else f"Install Gentoo — {self.step_title}")
        super().__init__(
            app, body, title=header,
            footer_keys=[("Enter", "Select / Edit"),
                         ("Tab", f"{back_label} / Continue"),
                         ("Esc", back_label)],
            help_text=self.help())
        self.configure_pane_cycle(cycle_container, cycle_positions,
                                  action_row=self._nav_row)
        self._render()

    def _compose_body(self):
        """Build the screen body. Returns (body, cycle_container, cycle_positions)
        for Tab pane-cycling. The default is the standard gate — a left step-rail
        beside the settings list; a gate can override this (e.g. the Welcome
        cover page). ``self._list`` and ``self._nav_row`` are already built."""
        # Right side is split 60/40: the settings list on top, a detail panel
        # below that explains the focused row. The Filler makes the (flow) Text a
        # box widget; valign="top" so short detail sits at the top, not centred.
        right = urwid.Pile([
            ("weight", 3, boxed(self._list, title=self.step_title)),
            ("weight", 2, boxed(urwid.Filler(self._detail_text, valign="top"),
                                title="Details")),
        ])
        cols = urwid.Columns(
            [(20, _rail_widget(self.step_key)), right],
            dividechars=1, focus_column=1)
        body = NavPile([("weight", 1, cols), ("pack", self._nav_row)])
        return body, body, [0]

    def _back(self) -> None:
        self.app.pop()

    def app_quit(self) -> None:
        """Exit the installer to the shell (the Welcome gate's 'Exit to Terminal')."""
        self.app.quit()

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
        self._row_meta = []
        for entry in self.setting_rows():
            if entry is None:
                items.append(urwid.Divider())
                self._actions.append(None)
                self._row_meta.append(None)
                continue
            label, value, action = entry
            text = label if value is None else f"{label:<24}: {value}"
            # Actionable rows are focusable (Enter edits); pure informational rows
            # (a heading, the proposed-partition table, the data-loss warning)
            # render as plain Text so the cursor can't land on — or highlight —
            # something there's nothing to do with.
            items.append(_row(text) if action is not None else urwid.Text(text))
            self._actions.append(action)
            # Only actionable rows key the detail panel; info rows keep it as-is.
            self._row_meta.append((label, value) if action is not None else None)
        self._walker[:] = items
        self._focus_first()
        pos = self._walker.get_focus()[1]
        if pos is not None:
            self._sync_detail(pos)

    def _sync_detail(self, position) -> None:
        """Refresh the bottom detail panel for the row now in focus. Wired to the
        walker's focus-changed callback, so it fires on every up/down move."""
        detail = getattr(self, "_detail_text", None)
        if detail is None:                      # a gate that skips the panel
            return
        meta = None
        if position is not None and 0 <= position < len(self._row_meta):
            meta = self._row_meta[position]
        if meta is None:
            detail.set_text(self.help())        # fallback: the whole-step help
            return
        label, value = meta
        detail.set_text(self.row_detail(label, value))

    def row_detail(self, label, value):
        """Detail-panel content for the focused row. Subclasses override to give
        per-row context; the default is the step's own help text so the panel is
        never empty."""
        return self.help()

    def _selectable_positions(self) -> list[int]:
        return [i for i, a in enumerate(self._actions) if a is not None]

    def _focus_first(self) -> None:
        sel = self._selectable_positions()
        if sel:
            self._walker.set_focus(sel[0])

    def handle_key(self, key):
        # Esc matches the Back/Exit button: quit to the shell at the root Welcome
        # gate, else step back to the previous gate.
        if key == "esc":
            self.app_quit() if self._exit_to_terminal else self._back()
            return None
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
            self._show_blocker(msg)
            return
        self.app.push(self._return_to() if self._return_to else self._next_screen())

    def _show_blocker(self, msg: str) -> None:
        """Surface a validation blocker as an attention-grabbing pop-up rather than
        an easy-to-miss red line in the footer."""
        modal = Modal(self.app, "Before you continue",
                      [urwid.Text(("error", msg))],
                      [("OK", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 62), height=("relative", 40))

    def _next_screen(self) -> Screen:
        nxt = _RAIL_KEYS[_RAIL_KEYS.index(self.step_key) + 1]
        return make_step(nxt, self.app, self.sel)


# --- gates -------------------------------------------------------------------

class LocalizationStep(WizardStep):
    step_key = "localization"
    step_title = "Welcome"
    header_title = ""          # cover page: no top-bar text, let the art stand alone

    def __init__(self, app, sel, *, return_to=None, exit_to_terminal=False):
        super().__init__(app, sel, return_to=return_to, exit_to_terminal=exit_to_terminal)
        # This gate is the wizard's entry screen, so it's constructed BEFORE
        # app.run() starts the loop — meaning is_running() is still False here and
        # we can't kick loop-bound work directly (that was the dead-clock bug). Arm
        # a one-shot alarm instead: it fires on the first loop iteration in the live
        # app, and never fires under tests (which build the screen but never run the
        # loop), keeping both the warm-up and the tick quiet there.
        self.app.main.set_alarm_in(0, self._on_shown)

    def _on_shown(self, *_):
        # Warm the network up in the BACKGROUND while the user reads the welcome and
        # sets localization — so we're likely online by the time they hit Continue
        # and can skip the Get Online gate entirely — and start the live clock.
        self.app.run_async(self._warm_network())
        self._tick_clock()

    def _tick_clock(self, *_):
        self._time_txt.set_text(("dim", dt_reader.clock_line(sep=".")))
        # keep ticking only while this gate is still on the stack (survives modals)
        if self in self.app._stack:
            self.app.main.set_alarm_in(1, self._tick_clock)

    def help(self) -> str:
        return ("Welcome to the Gentoo installer. Set your language/locale, timezone\n"
                "and keyboard — all offline, no network needed — then Continue.\n\n"
                "The network is coming up in the background; if it's ready you'll go\n"
                "straight to the next step, otherwise you'll be asked to connect.")

    async def _warm_network(self):
        """Best-effort: bring each wired link up + DHCP so connectivity is ready by
        Continue. Wi-Fi is skipped (it needs credentials — that's the Get Online
        gate's job). Reuses the GeST network stack (reader + link/dhcp commands)."""
        import contextlib

        from gest.core.exec.select import choose_executor
        from gest.core.network import commands as net_commands
        ex = choose_executor()
        try:
            ifaces = await self.app.run_blocking(net_reader.list_interfaces)
        except Exception:
            return
        for iface in ifaces:
            if (iface.loopback or iface.name.startswith(net_reader._WIFI_PREFIXES)
                    or (iface.up and iface.addresses)):
                continue
            with contextlib.suppress(Exception):
                await ex.run(net_commands.iplink_argv(iface.name, True))
                await ex.run(["dhcpcd", iface.name])

    def _next_screen(self) -> Screen:
        # Skip the Get Online gate when the background warm-up already got us online.
        if check_connectivity()[0]:
            return make_step("role", self.app, self.sel)
        return make_step("online", self.app, self.sel)

    def _compose_body(self):
        # The front door: a full-screen cover page with the GeST ASCII wordmark,
        # a welcome line, the localization pickers, and Back/Continue. No step-rail
        # here (the rail begins at the next gate) so the art has room to breathe.
        logo = urwid.Padding(urwid.Text(_GESI_LOGO_MARKUP, wrap="clip"),
                             align="center", width=_GESI_LOGO_W)
        self._time_txt = urwid.Text(("dim", dt_reader.clock_line(sep=".")), align="center")
        pile = NavPile([
            ("pack", urwid.Divider(" ")),
            ("pack", logo),
            ("pack", urwid.Divider(" ")),
            ("pack", urwid.Text(("title", "-Gentoo System Installer-"), align="center")),
            ("pack", urwid.Text(("dim", "Let's get started!"), align="center")),
            ("pack", self._time_txt),
            ("pack", urwid.Divider(" ")),
            ("pack", urwid.BoxAdapter(self._list, 4)),   # locale / tz / keyboard / clock
            ("pack", urwid.Divider(" ")),
            ("pack", self._nav_row),
        ])
        self._list_pos = 7    # 0 div,1 logo,2 div,3 title,4 subtitle,5 time,6 div,7 list
        panel = boxed(pile, title="Welcome!")
        body = urwid.Filler(
            urwid.Padding(panel, align="center", width=("relative", 72),
                          min_width=_GESI_LOGO_W + 6),
            valign="middle", height="pack")
        return body, pile, [self._list_pos]

    def setting_rows(self):
        clock = "Network (NTP sync)" if self.sel.clock == "chrony" else "Local (no sync)"
        return [
            ("Language / Locale", self.sel.locale, self._edit_locale),
            ("Timezone", self.sel.timezone, self._edit_timezone),
            ("Keyboard", self.sel.keymap, self._edit_keymap),
            ("Clock", clock, self._edit_clock),
        ]

    def _edit_clock(self):
        _choice_modal(self.app, "Clock", list(_CLOCK_LABELS.items()), self.sel.clock,
                      lambda k: setattr(self.sel, "clock", k), self._render)

    def _edit_timezone(self):
        _pick_modal(self.app, "Timezone", timezone_core.list_zones(),
                    self.sel.timezone, self._set("timezone"), self._render)

    def _edit_locale(self):
        # `locale -a` lists glibc's `C.utf8` form; sel.locale may be `C.UTF-8`.
        # Resolve to the list entry so the picker highlights the current value.
        choices = locale_core.list_locales()
        current = locale_core.match_in(self.sel.locale, choices)
        _pick_modal(self.app, "Language / Locale", choices, current,
                    self._set("locale"), self._render)

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
        return ("The installer downloads a stage3 and syncs Portage, so it needs a\n"
                "network connection. You only see this step because the background\n"
                "bring-up didn't get you online. Bring up a wired link, set up Wi-Fi\n"
                "(the GeST Wi-Fi module), then re-check.")

    def _online(self) -> bool:
        ok, _detail = check_connectivity()      # (bool, detail) — network probe
        return ok

    def _interfaces(self):
        try:
            return [i for i in net_reader.list_interfaces() if not i.loopback]
        except Exception:
            return []

    @staticmethod
    def _is_wifi(iface) -> bool:
        return iface.name.startswith(net_reader._WIFI_PREFIXES)

    def setting_rows(self):
        ifaces = self._interfaces()
        online = self._online()
        rows = [("Connectivity", "connected" if online else "NOT connected", None), None]
        if not ifaces:
            rows.append(("No usable network devices were found.", None, None))
            rows.append(("Check the adapter/cabling, then Re-check.", None, None))
            rows.append(None)
            rows.append(("Re-check connectivity", None, self._render))
            return rows
        for i in ifaces:
            kind = "Wi-Fi" if self._is_wifi(i) else "wired"
            addr = i.addresses[0] if i.addresses else "no address"
            rows.append((f"{i.name} ({kind})", f"{i.state.lower()}, {addr}", None))
        rows.append(None)
        rows.append(("Bring up wired network (DHCP)", None, self._dhcp))
        if any(self._is_wifi(i) for i in ifaces):
            rows.append(("Set up Wi-Fi…", None, self._wifi))
        rows.append(("Re-check connectivity", None, self._render))
        return rows

    def _dhcp(self):
        self.app.notify("Bringing up wired network (dhcpcd) …")
        self.app.run_async(self._run_dhcp())

    async def _run_dhcp(self):
        import contextlib

        from gest.core.exec.select import choose_executor
        with contextlib.suppress(Exception):
            await choose_executor().run(["dhcpcd"])
        self._render()

    def _wifi(self):
        # Fold in the GeST Wi-Fi module (scan/connect); Esc returns here, re-check.
        from gest.tui.screens.wifi import WifiScreen
        self.app.push(WifiScreen(self.app))

    def validate(self):
        if self._online():
            return None
        if not self._interfaces():
            return "No usable network devices — the install needs a connection."
        return "Not connected yet — bring a link up (or set up Wi-Fi), then Continue."

    def row_detail(self, label, value):
        if "(wired)" in label or "(Wi-Fi)" in label:
            return ("A network interface found on this machine, with its current "
                    "state and address. A wired link usually just needs DHCP; Wi-Fi "
                    "needs you to pick a network and enter its password.")
        if label.startswith("Bring up wired"):
            return ("Ask the wired interface to grab an address automatically over "
                    "DHCP — the usual case when a cable is plugged in. This runs "
                    "dhcpcd and then re-checks connectivity.")
        if label.startswith("Set up Wi-Fi"):
            return ("Open the Wi-Fi module to scan for networks and connect (pick an "
                    "SSID, enter the password). It returns here so you can re-check "
                    "once the link has associated.")
        if label.startswith("Re-check"):
            return ("Probe the network again after bringing a link up. Once this "
                    "reads 'connected', the install has everything it needs and you "
                    "can Continue.")
        return super().row_detail(label, value)


class RoleStep(WizardStep):
    step_key = "role"
    step_title = "System Role"

    # Descriptions deliberately DON'T name the admin/root style — that's proposed
    # per role but freely changed on the Account gate, so advertising it here is
    # misleading. Desktop gives our own Helm Desktop a friendly nudge.
    _ROLES = (
        ("desktop", "Desktop (HeDE)  — our own Helm Desktop, all hands on deck. Come aboard!"),
        ("server", "Server          — headless: SSH + firewall, ready to serve"),
        ("minimal", "Minimal         — base Gentoo, compiled from source, no desktop"),
        ("custom", "Custom          — start from Desktop and configure everything yourself"),
    )

    def help(self) -> str:
        return ("Pick what this machine is for. The role proposes a coherent set of\n"
                "defaults (build strategy, licenses, services, and a suggested admin\n"
                "model) that the later gates let you fine-tune — nothing here is locked in.")

    def setting_rows(self):
        out = [("Selected role", self.sel.role, None), None]
        for key, label in self._ROLES:
            mark = "◉" if key == self.sel.role else "○"
            out.append((f"{mark} {label}", None, self._choose(key)))
        return out

    _ROLE_DETAIL = {
        "desktop": "HeDE — our Helm Desktop — set up as a ready-to-use graphical "
                   "workstation: a Wayland session, everyday apps, and binary "
                   "packages so it comes up fast. The pick for a daily-driver laptop "
                   "or workstation.",
        "server": "A headless machine, no desktop — SSH and a firewall enabled, ready "
                  "to administer over the network. For a box that lives in a closet or "
                  "the cloud and quietly serves things.",
        "minimal": "Just base Gentoo, compiled from source, with no desktop and few "
                   "assumptions baked in. A clean foundation to build exactly what you "
                   "want on top of — or to learn the system from the ground up.",
        "custom": "Starts from the Desktop proposal but hands you the wheel: every "
                  "later gate is yours to reconfigure. Choose this when none of the "
                  "presets quite fit what you're after.",
    }

    def row_detail(self, label, value):
        for key, lbl in self._ROLES:
            if lbl in label:
                return self._ROLE_DETAIL[key]
        return super().row_detail(label, value)

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
        return (
            "GeSI proposes a whole-disk layout — like the Gentoo Handbook's\n"
            "example, but sized for this machine. Nothing is written now; the\n"
            "disk is partitioned and formatted only at the Install step, after\n"
            "you confirm at Review.\n"
            "\n"
            "The partitions it proposes:\n"
            "  • ESP (/boot/efi, vfat) — the EFI System Partition holds the\n"
            "    bootloader and kernels; UEFI firmware reads it directly. On\n"
            "    legacy BIOS you get a tiny raw BIOS-boot partition instead.\n"
            "  • swap — paging space for when RAM fills, and the store for\n"
            "    hibernation. Proposed = your RAM size (so you can hibernate),\n"
            "    up to 8 GiB; above that it's capped at 16 GiB, since past\n"
            "    8 GiB swap is overflow insurance, not hibernation-sized.\n"
            "  • root (/) — fills the rest: the whole system (/usr, /etc, and\n"
            "    your home, unless you split /home onto its own partition).\n"
            "\n"
            "You can edit any size or filesystem below. Installing ERASES\n"
            "EVERYTHING on the target disk — back up anything you need first.")

    def setting_rows(self):
        disks = [d for d in disk_reader.list_block_devices() if d.type == "disk"]
        rows = [
            ("Target disk", self._target_label(disks),
             lambda: self._pick_disk(disks)),
        ]
        if self.sel.disk:
            # Handbook-style context: the data-loss warning, then the concrete
            # partition table this proposal would create (derived from the real
            # DiskPlan so it can't drift from what actually gets written).
            rows.append(None)
            # `!` not `⚠`: the warning-sign glyph is missing from the plain
            # framebuffer console font (nomodeset), where it renders as a tofu
            # square. The `!` and the words carry the red `error` attr so the
            # data-loss line stands out; the rest of the sentence stays default.
            rows.append(([("error", "!"), "  Installing ",
                          ("error", "ERASES ALL DATA"),
                          f" on {self._target_label(disks)} — done at Install, "
                          "after you confirm at Review"], None, None))
            rows.append(None)
            rows.append(("Proposed layout:", None, None))
            rows.extend(self._partition_rows())
            warn = self._space_warning(disks)
            if warn:
                # Same nomodeset-safe `!` (red) instead of the ⚠ tofu square.
                rows.append(([("error", "  !  "), warn], None, None))
        rows.append(None)
        if self.sel.firmware != "bios":
            rows.append(("ESP size", self.sel.esp_size, self._edit_esp))
        rows.append(("Swap size", self.sel.swap_size or "(none)", self._edit_swap))
        rows.append(("Root filesystem", self.sel.root_fs, self._edit_root_fs))
        rows.append(("Separate /home", "yes" if self.sel.separate_home else "no",
                     self._edit_separate_home))
        if self.sel.separate_home:
            rows.append(("Root size", self.sel.root_size, self._edit_root_size))
            rows.append(("/home filesystem", self.sel.home_fs, self._edit_home_fs))
        # For Advanced (RAID / custom layouts), see the deferred plan
        # (docs/design/gesi-disk-phase.md — its own session).
        return rows

    def _target_label(self, disks) -> str:
        """The target disk with its size (``sda (238.5G)``), or the required-hint."""
        if not self.sel.disk:
            return "(none — required)"
        size = next((d.size for d in disks if d.name == self.sel.disk), "")
        return f"{self.sel.disk} ({size})" if size else self.sel.disk

    # -- detail panel ---------------------------------------------------------
    # Per-row copy for the bottom panel: teach the choice — what it is, why it
    # matters, and where the recommendation comes from — in plain language, so a
    # first-time installer can decide without a second screen or the Handbook.
    # Strings flow as one paragraph each (no hard line breaks mid-sentence) so
    # urwid word-wraps them to the panel's real width; \n\n marks a real break.
    _FS_DETAIL = {
        "ext4": "ext4 is the dependable default: mature, quick enough for anything, "
                "and understood by every tool and rescue disk out there. With no "
                "reason to prefer something else, this is the one.",
        "xfs": "xfs shines with large files and heavy parallel I/O — a favourite on "
               "servers and media stores. One thing to know: an xfs partition can "
               "grow later, but can never be shrunk.",
        "btrfs": "btrfs is a modern copy-on-write filesystem: point-in-time snapshots, "
                 "self-checksumming against silent corruption, and transparent "
                 "compression. More power, and a little more to learn.",
        "f2fs": "f2fs is built for flash — SSDs, eMMC, SD cards — laying data out to "
                "spread wear. A specialist pick; on an ordinary SSD, ext4 is just as "
                "happy and far more widely supported.",
        "ext3": "ext3 is ext4's predecessor, without extents or modern speed-ups. "
                "There's no reason to choose it today unless you're matching an older "
                "system that specifically needs it.",
    }

    def row_detail(self, label, value):
        if label == "Target disk":
            return self._disk_detail()
        if label == "ESP size":
            return ("The EFI System Partition is the first place UEFI firmware looks "
                    "at boot — a small FAT volume at /boot/efi holding the bootloader "
                    "and your kernels. Only a handful of kernels ever live here, so it "
                    f"stays small: 512M works, 1G leaves easy headroom (proposal: "
                    f"{self.sel.esp_size}). On legacy BIOS this becomes a tiny boot "
                    "partition and the size doesn't matter.")
        if label == "Swap size":
            return ("Swap is spillover space on disk for when RAM runs low, and where "
                    "memory is parked if you hibernate. To keep hibernate working it "
                    "needs to be at least your RAM size — which is why the proposal "
                    f"matches your installed memory, capped at 16G ({self.sel.swap_size or 'none'} "
                    "here). With plenty of RAM and no hibernate, a few gigs — or none "
                    "— is fine.")
        if label == "Root filesystem":
            return ("This formats root (/), the partition that carries the operating "
                    "system itself — and your home directory too, unless you split it "
                    "off below.\n\n"
                    + self._FS_DETAIL.get(value, f"{value} — a root filesystem."))
        if label == "/home filesystem":
            return ("This formats the separate /home partition — your documents, "
                    "downloads, and per-user settings.\n\n"
                    + self._FS_DETAIL.get(value, f"{value} — a filesystem."))
        if label == "Separate /home":
            return ("By default your files share a partition with the system. "
                    "Splitting /home onto its own partition draws a line between the "
                    "two: you can wipe and reinstall Gentoo without touching your "
                    "data, and a system that fills with logs or packages can't crowd "
                    "out your files. The cost is committing to a fixed root size now. "
                    "For a single-user desktop, one combined partition is perfectly "
                    "fine.")
        if label == "Root size":
            return ("With /home split off, root gets a fixed budget and /home takes "
                    "the rest. Root only holds the OS, installed packages and caches, "
                    "so it needn't be large — 30–60G suits most desktops. Give it more "
                    "if you compile heavily from source or install big toolchains, "
                    "which pile up under /var and /usr.")
        return super().row_detail(label, value)

    # The Target-disk note — the data-loss caution, verbatim. When a disk is
    # picked we append its current contents so you can confirm it's the right one.
    _DISK_NOTE = ("Your install is written to the selected disk. Make sure you have "
                  "the correct disk selected, a mistake here can be painful and "
                  "result in lost data.")

    def _disk_detail(self):
        if not self.sel.disk:
            return self._DISK_NOTE
        dev = next((d for d in disk_reader.list_block_devices()
                    if d.name == self.sel.disk), None)
        if dev is None:
            return self._DISK_NOTE
        if dev.children:
            tail = "\n".join(
                f"  {c.name:<12} {c.size:>8}  {c.fstype or '—'}"
                + (f"  {c.mountpoint}" if c.mountpoint else "")
                for c in dev.children)
        else:
            tail = "  (nothing partitioned — the disk looks empty)"
        return [self._DISK_NOTE + "\n\n",
                ("error", f"On {dev.name} ({dev.size}) right now — all of it erased:\n"),
                tail]

    def _build_plan(self):
        """The :class:`DiskPlan` the current selections would create, or ``None``
        if they're not yet valid (e.g. a bad size or a separate /home without a
        fixed root size) — so the breakdown mirrors exactly what gets written."""
        home_fs = self.sel.home_fs if self.sel.separate_home else None
        root_size = self.sel.root_size if self.sel.separate_home else "rest"
        try:
            if self.sel.firmware == "bios":
                return provision.bios_plan(
                    self.sel.disk, self.sel.swap_size, self.sel.root_fs,
                    root_size=root_size, home_fs=home_fs)
            return provision.uefi_plan(
                self.sel.disk, self.sel.esp_size, self.sel.swap_size,
                self.sel.root_fs, root_size=root_size, home_fs=home_fs)
        except ValueError:
            return None

    def _partition_rows(self):
        """One read-only row per proposed partition: number, mount, size, fs, why.

        Rendered verbatim (``value=None``) with compact self-aligned columns so it
        reads as a table even on a narrow (80-col) install console, instead of
        wasting the base row's 24-col label padding.
        """
        plan = self._build_plan()
        if plan is None:
            return [("  (adjust the sizes / filesystem below to see the layout)",
                     None, None)]
        fs_by_label = {f.label: f.kind for f in plan.filesystems}
        rows = []
        for p in plan.partitions:
            mount, purpose = _PART_PURPOSE.get(p.label, (p.label or "", ""))
            kind = fs_by_label.get(p.label, "—")
            size = "rest" if p.size == "rest" else p.size
            rows.append((f"  {p.number}. {mount:<10}{size:<6}{kind:<6}{purpose}",
                         None, None))
        return rows

    def _space_warning(self, disks) -> str | None:
        """The provision layer's too-small-root warning for this disk, or None."""
        disk_bytes = _size_to_bytes(
            next((d.size for d in disks if d.name == self.sel.disk), ""))
        if not disk_bytes:
            return None
        return provision.layout_warning(
            disk_bytes, _detect_ram_bytes(), self.sel.firmware)

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

    def _edit_separate_home(self):
        _choice_modal(
            self.app, "Separate /home partition",
            [("no", "No — one root partition (root fills the disk)"),
             ("yes", "Yes — split /home onto its own partition")],
            "yes" if self.sel.separate_home else "no",
            lambda k: setattr(self.sel, "separate_home", k == "yes"), self._render)

    def _edit_root_size(self):
        self._edit_text("Root size (e.g. 40G)", "root_size")

    def _edit_home_fs(self):
        from gest.core.disk.commands import ROOT_FS_KINDS
        opts = [(fs, fs) for fs in sorted(ROOT_FS_KINDS)]
        _choice_modal(self.app, "/home filesystem", opts, self.sel.home_fs,
                      self._set_attr("home_fs"), self._render)

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
        if not self.sel.disk:
            return "Select a target disk."
        if self.sel.separate_home and (not self.sel.root_size
                                       or self.sel.root_size == "rest"):
            return "Set a fixed root size for the separate /home layout."
        return None


class BaseSystemStep(WizardStep):
    step_key = "base"
    step_title = "Base System"

    def help(self) -> str:
        return ("How the base system is built, licensed, and administered. Binary\n"
                "packages are fast; compiling from source tunes to your CPU. The\n"
                "license rung sets ACCEPT_LICENSE; Features become system-wide USE.\n"
                "The admin model is how you become root. Your role has proposed sane\n"
                "values for all of these — a newcomer can just Continue; tweak to taste.")

    def setting_rows(self):
        build = "Binary packages (fast)" if self.sel.binary_pref else "Compile from source"
        feats = ", ".join(sorted(self.sel.capabilities)) or "(none)"
        rows = [
            ("Build strategy", build, self._edit_build),
            ("License policy", _LICENSE_LABELS[self.sel.license], self._edit_license),
            ("Features (USE)", feats, self._edit_features),
            ("Admin model", _ADMIN_LABELS[self.sel.admin_model], self._edit_admin),
        ]
        if self.sel.admin_model in ("sudo-augmented", "rootless"):
            rows.append(("Escalator", self.sel.escalator, self._edit_escalator))
        return rows

    # Detail keyed off the *currently selected* option, so the panel explains what
    # you have set (and how it differs from the alternatives) as you change it.
    _LICENSE_DETAIL = {
        "libre": "Accept only free/open-source licenses (@FREE). The most principled "
                 "choice, but you'll go without binary firmware and drivers like "
                 "NVIDIA's — some hardware won't work fully.",
        "redistributable": "Also accept licenses that are free to redistribute — "
                           "notably binary firmware and the NVIDIA driver — while "
                           "still refusing click-through EULAs. A practical middle "
                           "ground; the right default for most real hardware.",
        "full": "Accept everything, including click-through EULAs (some fonts, Steam, "
                "and the like). Maximum compatibility and the least fuss, with the "
                "least restrictive stance on licensing.",
    }
    _ADMIN_DETAIL = {
        "traditional": "The classic Unix setup: root has its own password and you "
                       "become root with su. Simple and familiar, but every admin "
                       "shares that one root password.",
        "sudo-augmented": "Root still has a password, and on top of that, administrator "
                          "users can run individual commands with sudo — so you rarely "
                          "need a full root shell. A comfortable balance.",
        "rootless": "The root account is locked — no direct root login. An administrator "
                    "account does all system work through sudo/doas, the model Ubuntu "
                    "and macOS use. You must create an admin user on the next gate.",
    }

    def row_detail(self, label, value):
        if label == "Build strategy":
            if self.sel.binary_pref:
                return ("Install prebuilt binary packages from a binhost — fast, easy "
                        "on the CPU, and the quickest route to a working system. You "
                        "can still compile individual packages later. Best on modest "
                        "hardware, or when you just want it up and running.")
            return ("Compile every package from source, tuned to your exact CPU and "
                    "USE flags — the classic Gentoo way. Slower (sometimes hours) but "
                    "maximally tailored. Best with capable hardware and some patience.")
        if label == "License policy":
            return self._LICENSE_DETAIL.get(self.sel.license, value)
        if label == "Features (USE)":
            return ("Features are high-level toggles that map to system-wide USE flags "
                    "— the switches that decide which optional support gets compiled "
                    "in (Bluetooth, printing, media codecs, and so on). Turning one on "
                    "enables it everywhere it applies. Your role has preselected a "
                    "sensible set; add or remove to taste.")
        if label == "Admin model":
            return self._ADMIN_DETAIL.get(self.sel.admin_model, value)
        if label == "Escalator":
            return ("How an administrator runs commands as root. sudo is the ubiquitous, "
                    "full-featured choice everyone knows. doas (from OpenBSD) is a much "
                    "smaller, simpler alternative with an easy config and less to go "
                    "wrong — plenty for a single-admin desktop.")
        return super().row_detail(label, value)

    def _edit_admin(self):
        opts = [(k, _ADMIN_LABELS[k]) for k in ADMIN_MODELS]
        _choice_modal(self.app, "Admin model", opts, self.sel.admin_model,
                      lambda k: setattr(self.sel, "admin_model", k), self._render)

    def _edit_escalator(self):
        _choice_modal(self.app, "Escalator", [("sudo", "sudo"), ("doas", "doas")],
                      self.sel.escalator,
                      lambda k: setattr(self.sel, "escalator", k), self._render)

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
        return ("The machine's hostname and accounts. Whether a root password is\n"
                "needed depends on the admin model (set on Base System): rootless\n"
                "locks the root account and needs an administrator account; the\n"
                "others set a root password.")

    def setting_rows(self):
        rows = [
            ("Hostname", self.sel.hostname, self._edit_hostname),
            None,
            ("Users", None, None),                          # section header
        ]
        for i, u in enumerate(self.sel.users):
            tag = "  (admin)" if u.admin else ""
            rows.append((f"   {u.name or '(unnamed)'}{tag}", None,
                         lambda i=i: self._edit_user(i)))
        rows.append(("   + Add user", None, lambda: self._edit_user(None)))
        rows.append(None)
        # Root is enabled (has a password) unless the admin model locks it (rootless).
        enabled = sets_root_password(self.sel.admin_model)
        rows.append(("Root", "enabled" if enabled else "disabled",
                     self._edit_rootpw if enabled else None))
        return rows

    def row_detail(self, label, value):
        if label == "Hostname":
            return ("The name this machine goes by — on the network and at the shell "
                    "prompt. Use lowercase letters, digits and hyphens, no spaces. "
                    "Pick something memorable, like 'workshop' or 'nimbus'.")
        if label.strip().startswith("+ Add user"):
            return ("Create a login account. You'll set its name and password, and can "
                    "mark it an administrator. On the rootless admin model that admin "
                    "account is how you do system tasks (via sudo/doas), so you need at "
                    "least one.")
        if label.startswith("   "):        # an existing user row
            return ("A login account you've defined. Press Enter to edit its name, "
                    "password, or admin flag. '(admin)' means it can perform system "
                    "administration through sudo/doas.")
        if label == "Root":
            if sets_root_password(self.sel.admin_model):
                return ("The superuser account. Under this admin model root has a "
                        "password — set it here — and you become root with su (or "
                        "sudo). Keep it strong: root can do anything on the system.")
            return ("This admin model (rootless) locks the root account — there's no "
                    "direct root login. System tasks go through an administrator "
                    "account with sudo/doas instead, so be sure you added one above.")
        return super().row_detail(label, value)

    def _edit_hostname(self):
        self._edit_text("Hostname", "hostname")

    def _edit_user(self, index=None):
        # index None → add a new account; otherwise edit sel.users[index]. Clearing
        # the name of an existing account removes it.
        editing = index is not None
        draft = self.sel.users[index] if editing else UserDraft()
        name = urwid.Edit("Name              : ", draft.name)
        comment = urwid.Edit("Full name/comment : ", draft.comment)
        admin = urwid.CheckBox("Administrator account", state=draft.admin)
        pw = urwid.Edit("Password          : ", draft.password, mask="*")
        pw2 = urwid.Edit("Confirm           : ", draft.password, mask="*")

        def save():
            uname = name.edit_text.strip()
            if not uname:
                if editing:
                    del self.sel.users[index]            # cleared name → remove
                self.app.pop()
                self._render()
                return
            if not valid_user_name(uname):
                self.app.notify("Invalid user name.", error=True)
                return
            if pw.edit_text != pw2.edit_text:
                self.app.notify("Passwords do not match.", error=True)
                return
            draft.name = uname
            draft.comment = comment.edit_text.strip()
            draft.admin = admin.state
            draft.password = pw.edit_text
            if not editing:
                self.sel.users.append(draft)
            self.app.pop()
            self._render()

        def remove():
            if editing:
                del self.sel.users[index]
            self.app.pop()
            self._render()

        buttons = [("Save", save)]
        if editing:
            buttons.append(("Remove", remove))
        buttons.append(("Cancel", self.app.pop))
        modal = Modal(self.app, "User account",
                      [urwid.Text(("hint", "An everyday account. Turn on Administrator "
                                           "to let it install software and change "
                                           "settings; a password lets it log in.")),
                       urwid.Divider(), name, comment, admin, pw, pw2],
                      buttons)
        self.app.push_modal(modal, width=("relative", 70), height=("relative", 66))

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
        # Every account you name has to be usable: a valid name and a password.
        for u in self.sel.users:
            if not u.name:
                continue
            if not valid_user_name(u.name):
                return f"“{u.name}” isn't a valid user name."
            if not u.password:
                return f"Give {u.name} a password — it's needed to log in."
        if sets_root_password(self.sel.admin_model):
            if not self.sel.root_password:
                return ("Set a root password (or choose the Rootless admin model on "
                        "Base System).")
        elif not any(valid_user_name(u.name) and u.admin for u in self.sel.users):
            return ("This setup needs an administrator account.\n\n"
                    "In the Users list, add a user and turn on “Administrator account”.")
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


def start(app: App, *, exit_to_terminal: bool = False) -> Screen:
    """The wizard's first gate (Welcome), seeded with the Desktop proposal.

    ``exit_to_terminal`` = True for the standalone installer (``gest --install`` on
    the live medium): the Welcome gate's first button reads "Exit to Terminal" and
    quits to the shell. False when launched from the GeST menu, where it stays a
    "Back" that returns to the menu.
    """
    return LocalizationStep(app, assemble.propose("desktop"),
                            exit_to_terminal=exit_to_terminal)
