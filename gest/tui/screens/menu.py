"""The two-pane YaST-style Control Center (urwid)."""

from __future__ import annotations

import urwid

from gest.tui.runtime import App, Screen
from gest.tui.screens.apply import ApplyScreen, depclean_plan, sync_plan, world_plan
from gest.tui.screens.bootloader import BootloaderScreen
from gest.tui.screens.eselect import EselectScreen
from gest.tui.screens.network import NetworkScreen
from gest.tui.screens.news import NewsScreen
from gest.tui.screens.services import ServicesScreen
from gest.tui.screens.software import SoftwareScreen
from gest.tui.screens.system import HostnameScreen, LocaleScreen, TimezoneScreen
from gest.tui.screens.users import UsersScreen

# Category → [(module_key, label, implemented)]. All modules are implemented.
CATEGORIES: list[tuple[str, list[tuple[str, str, bool]]]] = [
    ("Software", [
        ("software", "Software Management", True),
        ("update", "System Update", True),
        ("depclean", "Clean Up Packages", True),
        ("sync", "Sync Portage Tree", True),
        ("news", "Portage News", True),
    ]),
    ("System", [
        ("hostname", "Hostname", True),
        ("timezone", "Timezone", True),
        ("locale", "Locale", True),
        ("eselect", "eselect (selections)", True),
        ("bootloader", "Bootloader & Kernel", True),
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
                (30, urwid.LineBox(self._left, title="Categories")),
                urwid.LineBox(self._right, title="Modules"),
            ],
            dividechars=1,
        )
        super().__init__(
            app, self._columns, title="GeST Control Center",
            footer_keys=[("Enter", "Run"), ("→", "Modules"), ("F9", "Quit")],
        )
        urwid.connect_signal(self._cat_walker, "modified", self._on_cat_change)
        self._populate_modules(0)

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
            self.app.push(SoftwareScreen(self.app))
        elif key == "update":
            self.app.push(ApplyScreen(self.app, [world_plan()], verb="System update"))
        elif key == "depclean":
            self.app.push(ApplyScreen(self.app, [depclean_plan()], verb="Clean up"))
        elif key == "sync":
            self.app.push(ApplyScreen(self.app, [sync_plan()], verb="Sync"))
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
        elif key == "users":
            self.app.push(UsersScreen(self.app))
        elif key == "network":
            self.app.push(NetworkScreen(self.app))
        else:
            self.app.notify(f"“{key}” isn't ported to the urwid frontend yet.")

    def handle_key(self, key):
        if key == "f9":
            self.app.quit()
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
