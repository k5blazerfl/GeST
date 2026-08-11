"""make.conf editor (urwid): list variables, edit a value, add a variable.

Reading is unprivileged; writing goes through the polkit-gated Portage backend
(PortageBackend.write_config → portage.configure).
"""

from __future__ import annotations

import urwid

from gest.core.makeconf import reader, writer
from gest.core.makeconf.reader import Var
from gest.core.portage.backend_client import PortageBackend
from gest.tui.runtime import App, Modal, Screen, boxed


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


class MakeconfScreen(Screen):
    def __init__(self, app: App) -> None:
        self._vars: list[Var] = []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, boxed(self._list, title="/etc/portage/make.conf"),
            title="make.conf",
            footer_keys=[("Enter", "Edit"), ("a", "Add"), ("Esc", "Back")],
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        self._vars = await self.app.run_blocking(reader.read_makeconf)
        self._walker[:] = [
            _row(f"{v.name:<20} {v.value}") for v in self._vars
        ] or [urwid.Text(" (empty)")]
        if self._vars:
            self._walker.set_focus(0)
        self.app.refresh()

    def _current(self) -> Var | None:
        if self._vars and 0 <= self._walker.focus < len(self._vars):
            return self._vars[self._walker.focus]
        return None

    async def _apply(self, name: str, value: str) -> None:
        write = await self.app.run_blocking(lambda: writer.set_variable(name, value))
        backend = PortageBackend()
        try:
            await backend.connect()
            ok = await backend.write_config([write])
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        self.app.notify(f"set {name}" if ok else f"failed to set {name}", error=not ok)
        await self._load()

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key in ("enter", "e"):
            var = self._current()
            if var is not None:
                self._edit(var)
            return None
        if key == "a":
            self._add()
            return None
        return key

    def _edit(self, var: Var) -> None:
        value = urwid.Edit("Value: ", var.value)

        def save():
            val = value.edit_text.strip()
            if not reader.valid_value(val):
                self.app.notify('Invalid value (no " ` $( or newlines).', error=True)
                return
            self.app.pop()
            self.app.run_async(self._apply(var.name, val))

        modal = Modal(
            self.app, f"Edit {var.name}",
            [urwid.Text(f"{var.name} ="), urwid.Divider(), value],
            [("Save", save), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 80), height=("relative", 55))

    def _add(self) -> None:
        name = urwid.Edit("Name: ")
        value = urwid.Edit("Value: ")

        def save():
            n = name.edit_text.strip()
            val = value.edit_text.strip()
            if not reader.valid_name(n):
                self.app.notify("Invalid variable name.", error=True)
                return
            if not reader.valid_value(val):
                self.app.notify('Invalid value (no " ` $( or newlines).', error=True)
                return
            self.app.pop()
            self.app.run_async(self._apply(n, val))

        modal = Modal(
            self.app, "Add make.conf variable", [name, value],
            [("Save", save), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 80), height=("relative", 55))
