"""A YaST-style menu bar with keyboard-driven dropdown menus.

Textual has no native menubar. This renders a row of titles
(``[Dependencies▾][View▾]…``); Left/Right move between them, Down/Enter opens a
dropdown, Up/Down pick an item, Enter selects (posting :class:`MenuBar.Selected`
with the menu id + item id) and Esc closes. The dropdown is mounted on the
screen's ``overlay`` layer so it floats above the content.

Menu spec: ``[(menu_id, title, [(item_id, label, enabled), …]), …]``.
"""

from __future__ import annotations

from textual import events
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

MenuSpec = list[tuple[str, str, list[tuple[str, str, bool]]]]


class _MenuTitle(Static):
    can_focus = True

    def __init__(self, menu_id: str, title: str) -> None:
        self.menu_id = menu_id
        super().__init__(f" {title} ", classes="menu-title", id=f"menu-{menu_id}")


class _Dropdown(OptionList):
    """The open menu; self-contained so its events don't need the screen."""

    def __init__(self, menubar: MenuBar, items: list[tuple[str, str, bool]]) -> None:
        self._menubar = menubar
        options = [
            Option(label, id=item_id, disabled=not enabled)
            for item_id, label, enabled in items
        ]
        super().__init__(*options, id="menu-dropdown")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self._menubar._select(event.option.id)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self._menubar._close(refocus=True)


class MenuBar(Horizontal):
    DEFAULT_CSS = """
    MenuBar {
        height: 1;
        dock: top;
        background: $panel;
        color: $text;
    }
    MenuBar > .menu-title {
        padding: 0 1;
    }
    MenuBar > .menu-title:focus {
        text-style: bold;
        background: $primary;
        color: $text;
    }
    #menu-dropdown {
        layer: overlay;
        width: auto;
        min-width: 24;
        height: auto;
        max-height: 16;
        border: round $primary;
        background: $panel;
    }
    """

    class Selected(Message):
        def __init__(self, menu: str, item: str) -> None:
            self.menu = menu
            self.item = item
            super().__init__()

    def __init__(self, menus: MenuSpec, **kwargs) -> None:
        self._menus = menus
        self._items = {menu_id: items for menu_id, _title, items in menus}
        self._dropdown: _Dropdown | None = None
        self._open_menu: str | None = None
        super().__init__(**kwargs)

    def compose(self):
        for menu_id, title, _items in self._menus:
            yield _MenuTitle(menu_id, f"{title}▾")

    # -- keyboard on the title row -----------------------------------------

    def on_key(self, event: events.Key) -> None:
        title = self.app.focused
        if not isinstance(title, _MenuTitle):
            return
        titles = list(self.query(_MenuTitle))
        idx = titles.index(title)
        if event.key == "right":
            titles[(idx + 1) % len(titles)].focus()
            event.stop()
        elif event.key == "left":
            titles[(idx - 1) % len(titles)].focus()
            event.stop()
        elif event.key in ("down", "enter", "space"):
            self._open(title)
            event.stop()

    # -- open / close / select ---------------------------------------------

    def _open(self, title: _MenuTitle) -> None:
        self._close()
        self._open_menu = title.menu_id
        self._dropdown = _Dropdown(self, self._items[title.menu_id])
        self.screen.mount(self._dropdown)
        self._dropdown.styles.offset = (title.region.x, 1)
        self._dropdown.focus()

    def _close(self, refocus: bool = False) -> None:
        menu = self._open_menu
        if self._dropdown is not None:
            self._dropdown.remove()
            self._dropdown = None
        self._open_menu = None
        if refocus and menu is not None:
            self.query_one(f"#menu-{menu}", _MenuTitle).focus()

    def _select(self, item_id: str) -> None:
        menu = self._open_menu
        self._close(refocus=True)
        if menu is not None:
            self.post_message(self.Selected(menu, item_id))
