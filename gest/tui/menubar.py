"""A YaST-style dropdown menu bar for urwid.

A row of titles; Left/Right move between them, Down/Enter opens the highlighted
menu as a floating dropdown, Up/Down pick an item, Enter selects (calls
``on_select(menu_id, item_id)``), Esc closes. Menu spec:
``[(menu_id, title, [(item_id, label, enabled), …]), …]``.
"""

from __future__ import annotations

from collections.abc import Callable

import urwid

from gest.tui.runtime import App, boxed

MenuSpec = list


class _MenuTitle(urwid.WidgetWrap):
    def __init__(self, menu_id: str, title: str):
        self.menu_id = menu_id
        self.label = f" {title} "
        self.width = len(self.label)
        super().__init__(urwid.AttrMap(urwid.SelectableIcon(self.label, 0),
                                       "menu_title", focus_map="menu_focus"))


class _Dropdown(urwid.WidgetWrap):
    def __init__(self, app: App, menu_id: str, items: list, on_select: Callable):
        self.app = app
        self.menu_id = menu_id
        self.on_select = on_select
        self._ids: list[str | None] = []
        rows = []
        for item_id, label, enabled in items:
            text = f" {label} "
            if enabled:
                rows.append(urwid.AttrMap(urwid.SelectableIcon(text, 0), None, "menu_focus"))
                self._ids.append(item_id)
            else:
                rows.append(urwid.Text(("dim", text)))
                self._ids.append(None)
        self.width = max((len(label) for _i, label, _e in items), default=8) + 4
        self.height = len(items) + 2
        self._walker = urwid.SimpleFocusListWalker(rows)
        for i, iid in enumerate(self._ids):
            if iid is not None:
                self._walker.set_focus(i)
                break
        listbox = urwid.ListBox(self._walker)
        super().__init__(urwid.AttrMap(boxed(listbox), "menu_drop"))

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if key == "esc":
            self.app.pop()
            return None
        if key == "enter":
            iid = self._ids[self._walker.focus]
            self.app.pop()
            if iid is not None:
                self.on_select(self.menu_id, iid)
            return None
        return key


class MenuBar(urwid.WidgetWrap):
    def __init__(self, app: App, menus: MenuSpec, on_select: Callable,
                 *, top: int = 2):
        self.app = app
        self._menus = menus
        self.on_select = on_select
        self._top = top
        self._titles = [_MenuTitle(mid, title) for mid, title, _ in menus]
        self._cols = urwid.Columns([("pack", t) for t in self._titles], dividechars=1)
        super().__init__(urwid.AttrMap(self._cols, "menubar"))

    def keypress(self, size, key):
        key = super().keypress(size, key)  # Columns handles left/right
        if key in ("down", "enter", " "):
            self._open()
            return None
        return key

    def _open(self) -> None:
        idx = self._cols.focus_position
        menu_id, _title, items = self._menus[idx]
        left = sum(t.width + 1 for t in self._titles[:idx])
        drop = _Dropdown(self.app, menu_id, items, self.on_select)
        self.app.push_overlay(drop, align="left", left=left, valign="top",
                              top=self._top, width=drop.width, height=drop.height)
