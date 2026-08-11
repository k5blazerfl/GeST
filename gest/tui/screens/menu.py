"""The two-pane YaST-style Control Center (urwid)."""

from __future__ import annotations

import socket

import urwid

from gest import __version__
from gest.tui.runtime import App, NavPile, Screen, boxed, focusable_actions
from gest.tui.screens.bootloader import BootloaderScreen
from gest.tui.screens.cleanup import CleanupScreen
from gest.tui.screens.datetime import DateTimeScreen
from gest.tui.screens.disk import DiskScreen
from gest.tui.screens.eselect import EselectScreen
from gest.tui.screens.hardware import HardwareScreen
from gest.tui.screens.hwflags import HwFlagsScreen
from gest.tui.screens.licenses import LicensesScreen
from gest.tui.screens.logs import LogsScreen
from gest.tui.screens.makeconf import MakeconfScreen
from gest.tui.screens.network import NetworkScreen
from gest.tui.screens.news import NewsScreen
from gest.tui.screens.repos import ReposScreen
from gest.tui.screens.services import ServicesScreen
from gest.tui.screens.software import SoftwareLoadingScreen
from gest.tui.screens.sync import SyncScreen
from gest.tui.screens.system import HostnameScreen, LocaleScreen, TimezoneScreen
from gest.tui.screens.update import UpdateScreen
from gest.tui.screens.users import UsersScreen

# Category → [(module_key, label, implemented)]. All modules are implemented.
CATEGORIES: list[tuple[str, list[tuple[str, str, bool]]]] = [
    ("Software", [
        ("software", "Software Management", True),
        ("repositories", "Software Repositories", True),
        ("update", "System Update", True),
        ("depclean", "Clean Up Packages", True),
        ("sync", "Sync Portage Tree", True),
        ("news", "Portage News", True),
        ("licenses", "Package Licenses", True),
    ]),
    ("System", [
        ("hostname", "Hostname", True),
        ("timezone", "Timezone", True),
        ("locale", "Locale", True),
        ("eselect", "eselect (selections)", True),
        ("bootloader", "Bootloader & Kernel", True),
        ("makeconf", "make.conf editor", True),
        ("datetime", "Date & Time", True),
    ]),
    ("Hardware", [
        ("hardware", "Hardware Information", True),
        ("hwflags", "CPU & Video Flags", True),
    ]),
    ("Storage", [
        ("disk", "Disks & Mounts", True),
    ]),
    ("Services", [
        ("services", "Services (OpenRC)", True),
    ]),
    ("Security and Users", [
        ("users", "Users & Groups", True),
    ]),
    ("Network", [
        ("network", "Network", True),
    ]),
    ("Miscellaneous", [
        ("logs", "System Logs", True),
    ]),
]


def _icon(label: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(label, 0), None, focus_map="focus")


class MenuScreen(Screen):
    def __init__(self, app: App) -> None:
        cats = [_icon(name) for name, _mods in CATEGORIES]
        self._cat_walker = urwid.SimpleFocusListWalker(cats)
        self._left = urwid.ListBox(self._cat_walker)

        self._mod_walker = urwid.SimpleFocusListWalker([])
        self._mod_keys: list[str] = []
        self._right = urwid.ListBox(self._mod_walker)

        self._columns = urwid.Columns(
            [
                (30, boxed(self._left)),
                boxed(self._right),
            ],
            dividechars=1,
        )
        title_box = boxed(
            urwid.Text(("cc_title", "GeST Control Center"), align="center"))
        self._actions = focusable_actions([
            ("Help", self.show_help), ("Quit", app.quit)])
        body = NavPile([
            ("pack", title_box),
            ("pack", urwid.Divider()),
            self._columns,
            ("pack", urwid.Divider()),
            ("pack", self._actions),
        ])
        super().__init__(
            app, body, title=f"GeST v{__version__} — menu @ {socket.gethostname()}",
            footer_keys=[("F9", "Quit")],
            help_text=(
                "GeST Control Center — a YaST-style front-end for Gentoo.\n\n"
                "↑/↓   move within a pane\n"
                "→/Enter   open a category / run a module\n"
                "R   run the highlighted module\n"
                "Esc/←   go back to the categories\n"
                "F9/Q   quit"
            ),
        )
        self.configure_pane_cycle(body, [2], action_row=self._actions)
        self._refresh_footer()
        urwid.connect_signal(self._cat_walker, "modified", self._on_cat_change)
        self._populate_modules(0)

    def _footer_context(self):
        if self._on_action_row():
            return [("Enter", "Activate"), ("Tab", "Next"), ("F9", "Quit")]
        if self._columns.focus_position == 0:
            return [("Enter", "Open"), ("→", "Modules"), ("Tab", "Buttons"),
                    ("F9", "Quit")]
        return [("Enter", "Run"), ("Esc/←", "Categories"), ("Tab", "Buttons"),
                ("F9", "Quit")]

    def _on_cat_change(self) -> None:
        self._populate_modules(self._cat_walker.focus)

    def _populate_modules(self, cat_index: int) -> None:
        _name, modules = CATEGORIES[cat_index]
        self._mod_keys = [key for key, _label, _impl in modules]
        items = []
        for _key, label, impl in modules:
            text = label if impl else f"{label}  (not ported)"
            items.append(_icon(text))
        self._mod_walker[:] = items
        if items:
            self._mod_walker.set_focus(0)

    def _launch(self, key: str) -> None:
        if key == "news":
            self.app.push(NewsScreen(self.app))
        elif key == "software":
            self.app.push(SoftwareLoadingScreen(self.app))
        elif key == "update":
            self.app.push(UpdateScreen(self.app))
        elif key == "depclean":
            self.app.push(CleanupScreen(self.app))
        elif key == "sync":
            self.app.push(SyncScreen(self.app))
        elif key == "repositories":
            self.app.push(ReposScreen(self.app))
        elif key == "licenses":
            self.app.push(LicensesScreen(self.app))
        elif key == "services":
            self.app.push(ServicesScreen(self.app))
        elif key == "hostname":
            self.app.push(HostnameScreen(self.app))
        elif key == "timezone":
            self.app.push(TimezoneScreen(self.app))
        elif key == "locale":
            self.app.push(LocaleScreen(self.app))
        elif key == "eselect":
            self.app.push(EselectScreen(self.app))
        elif key == "bootloader":
            self.app.push(BootloaderScreen(self.app))
        elif key == "makeconf":
            self.app.push(MakeconfScreen(self.app))
        elif key == "datetime":
            self.app.push(DateTimeScreen(self.app))
        elif key == "hardware":
            self.app.push(HardwareScreen(self.app))
        elif key == "hwflags":
            self.app.push(HwFlagsScreen(self.app))
        elif key == "disk":
            self.app.push(DiskScreen(self.app))
        elif key == "users":
            self.app.push(UsersScreen(self.app))
        elif key == "network":
            self.app.push(NetworkScreen(self.app))
        elif key == "logs":
            self.app.push(LogsScreen(self.app))
        else:
            self.app.notify(f"“{key}” isn't ported to the urwid frontend yet.")

    def _run_focused(self) -> None:
        if self._mod_keys:
            self._launch(self._mod_keys[self._mod_walker.focus])

    def handle_key(self, key):
        if key in ("f9", "q", "Q"):  # quit is a top-level action (see App._unhandled)
            self.app.quit()
            return None
        if key in ("h", "H"):  # F1 is handled by the Screen base
            self.show_help()
            return None
        if key in ("r", "R"):
            self._run_focused()
            return None
        if key == "enter":
            if self._columns.focus_position == 0:
                self._columns.focus_position = 1
            elif self._mod_keys:
                self._launch(self._mod_keys[self._mod_walker.focus])
            return None
        if key == "esc" and self._columns.focus_position == 1:
            self._columns.focus_position = 0
            return None
        return key
