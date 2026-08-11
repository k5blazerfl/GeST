"""eselect module (urwid): two-pane modules | targets, switch the selection.

Reading is unprivileged (`eselect … list`); switching a target goes through the
polkit-gated EselectBackend.
"""

from __future__ import annotations

import urwid

from gest.core.eselect import reader
from gest.core.eselect.backend_client import EselectBackend
from gest.core.eselect.model import Module, Target
from gest.tui.runtime import App, Screen, boxed


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


class EselectScreen(Screen):
    def __init__(self, app: App) -> None:
        self._modules: list[Module] = []
        self._targets: list[Target] = []
        self._current_module = ""
        self._mod_walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._left = urwid.ListBox(self._mod_walker)
        self._tgt_walker = urwid.SimpleFocusListWalker([])
        self._right = urwid.ListBox(self._tgt_walker)
        self._columns = urwid.Columns(
            [(28, boxed(self._left, title="Modules")),
             boxed(self._right, title="Targets")],
            dividechars=1,
        )
        super().__init__(
            app, self._columns, title="eselect",
            footer_keys=[("Enter", "Set"), ("→", "Targets"), ("Esc", "Back")],
        )
        self.configure_pane_cycle(self._columns, [0, 1])   # Tab mirrors ←/→
        self._refresh_footer()
        urwid.connect_signal(self._mod_walker, "modified", self._on_module)
        app.run_async(self._load_modules())

    def _footer_context(self):
        if self._columns.focus_position == 0:              # Modules
            return [("Enter", "Targets"), ("→", "Targets"), ("Esc", "Back")]
        return [("Enter", "Set"), ("←", "Modules"), ("Esc", "Back")]

    async def _load_modules(self) -> None:
        mods = await self.app.run_blocking(reader.list_modules)
        self._modules = mods
        self._mod_walker[:] = [_row(m.name) for m in mods] or [urwid.Text(" (none)")]
        if mods:
            self._mod_walker.set_focus(0)  # fires _on_module -> loads targets
        self.app.refresh()

    def _on_module(self) -> None:
        if self._modules and 0 <= self._mod_walker.focus < len(self._modules):
            self.app.run_async(self._load_targets(self._modules[self._mod_walker.focus].name))

    async def _load_targets(self, module: str) -> None:
        self._current_module = module
        targets = await self.app.run_blocking(reader.list_targets, module)
        self._targets = targets
        self._tgt_walker[:] = [
            _row(f"{'●' if t.current else ' '} [{t.number}] {t.name}") for t in targets
        ] or [urwid.Text(" (no selectable targets)")]
        cur = next((i for i, t in enumerate(targets) if t.current), 0)
        if targets:
            self._tgt_walker.set_focus(cur)
        self.app.refresh()

    async def _set(self, module: str, number: int) -> None:
        backend = EselectBackend()
        try:
            await backend.connect()
            ok, out = await backend.set_target(module, number)
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        self.app.notify(out or ("done" if ok else "failed"), error=not ok)
        await self._load_targets(module)

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key == "enter":
            if self._columns.focus_position == 0:
                self._columns.focus_position = 1
            elif self._targets:
                target = self._targets[self._tgt_walker.focus]
                self.app.run_async(self._set(self._current_module, target.number))
            return None
        return key
