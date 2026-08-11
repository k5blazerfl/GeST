"""Hardware information (urwid): two-pane categories | details, read-only.

Everything is read unprivileged (`lscpu`, `lspci`, `lsusb`, `lsblk`,
/proc/meminfo, /sys/class/dmi/id) — there is no backend and no polkit here.
"""

from __future__ import annotations

import urwid

from gest.core.hardware import reader
from gest.core.hardware.model import Section
from gest.tui.runtime import App, Screen, boxed


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


class HardwareScreen(Screen):
    def __init__(self, app: App) -> None:
        self._sections: list[Section] = []
        self._cat_walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._left = urwid.ListBox(self._cat_walker)
        self._detail_walker = urwid.SimpleFocusListWalker([])
        self._right = urwid.ListBox(self._detail_walker)
        self._columns = urwid.Columns(
            [(24, boxed(self._left, title="Hardware")),
             boxed(self._right, title="Details")],
            dividechars=1,
        )
        super().__init__(
            app, self._columns, title="Hardware Information",
            footer_keys=[("→", "Details"), ("Esc", "Back")],
        )
        urwid.connect_signal(self._cat_walker, "modified", self._on_section)
        app.run_async(self._load())

    async def _load(self) -> None:
        sections = await self.app.run_blocking(reader.inventory)
        self._sections = sections
        self._cat_walker[:] = [_row(s.title) for s in sections] or [urwid.Text(" (none)")]
        if sections:
            self._cat_walker.set_focus(0)  # fires _on_section → fills the detail pane
        self.app.refresh()

    def _on_section(self) -> None:
        if not self._sections:
            return
        idx = self._cat_walker.focus
        if not 0 <= idx < len(self._sections):
            return
        lines = self._sections[idx].lines or ["(nothing reported — tool not installed?)"]
        self._detail_walker[:] = [_row(line) for line in lines]
        self._detail_walker.set_focus(0)
        self.app.refresh()

    def handle_key(self, key):
        if key == "esc":
            if self._columns.focus_position == 1:
                self._columns.focus_position = 0  # details → back to categories
            else:
                self.app.pop()
            return None
        if key == "enter" and self._columns.focus_position == 0:
            self._columns.focus_position = 1
            return None
        return key
