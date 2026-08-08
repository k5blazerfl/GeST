"""The two-pane YaST-style Control Center (urwid)."""

from __future__ import annotations

import urwid

from gest.uwui.runtime import App, Screen
from gest.uwui.screens.news import NewsScreen

# Category → [(module_key, label, implemented)]. Mirrors the Textual frontend;
# only modules ported to urwid so far are launchable.
CATEGORIES: list[tuple[str, list[tuple[str, str, bool]]]] = [
    ("Software", [
        ("software", "Software Management", False),
        ("update", "System Update", False),
        ("depclean", "Clean Up Packages", False),
        ("sync", "Sync Portage Tree", False),
        ("news", "Portage News", True),
    ]),
    ("System", [
        ("hostname", "Hostname", False),
        ("timezone", "Timezone", False),
        ("locale", "Locale", False),
    ]),
    ("Services", [
        ("services", "Services (OpenRC)", False),
    ]),
    ("Security and Users", [
        ("users", "Users & Groups", False),
    ]),
    ("Network", [
        ("network", "Network", False),
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
