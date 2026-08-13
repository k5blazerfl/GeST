"""Environment variables (env.d) in urwid: edit the GeST /etc/env.d drop-in.

Reads the managed drop-in unprivileged; applying goes through the polkit-gated
EnvdBackend, which writes the drop-in and runs `env-update`.
"""

from __future__ import annotations

import contextlib

import urwid

from gest.core.envd import config, reader
from gest.core.envd.backend_client import EnvdBackend
from gest.tui.runtime import App, Modal, Screen, boxed


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


class EnvdScreen(Screen):
    def __init__(self, app: App) -> None:
        self._vars: dict[str, str] = {}
        self._names: list[str] = []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, boxed(self._list, title="/etc/env.d/99gest"),
            title="Environment (env.d)",
            footer_keys=[("a", "Add"), ("e", "Edit"), ("d", "Remove"), ("Esc", "Back")],
        )
        self._load()

    def _load(self) -> None:
        self._vars = reader.current_vars()
        self._names = sorted(self._vars)
        rows = [_row(f'{n}="{self._vars[n]}"') for n in self._names] or \
            [urwid.Text(" (no GeST-managed variables)")]
        self._walker[:] = rows
        if self._names:
            self._walker.set_focus(min(self._walker.focus or 0, len(self._names) - 1))
        self.app.refresh()

    def _current(self) -> str | None:
        if not self._names:
            return None
        idx = self._walker.focus
        return self._names[idx] if idx is not None and 0 <= idx < len(self._names) else None

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key == "a":
            self._form(None)
            return None
        cur = self._current()
        if key == "e" and cur is not None:
            self._form(cur)
            return None
        if key == "d" and cur is not None:
            updated = {n: v for n, v in self._vars.items() if n != cur}
            self._apply(updated)
            return None
        return key

    def _apply(self, variables: dict[str, str]) -> None:
        self.app.run_async(self._call(variables))

    async def _call(self, variables: dict[str, str]) -> None:
        backend = EnvdBackend()
        try:
            await backend.connect()
            ok, out = await backend.apply_vars(variables)
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            with contextlib.suppress(Exception):
                await backend.close()
            return
        with contextlib.suppress(Exception):
            await backend.close()
        self.app.notify(out or ("done" if ok else "failed"), error=not ok)
        if ok:
            self._load()

    def _form(self, existing: str | None) -> None:
        name = urwid.Edit("Name  : ", existing or "")
        value = urwid.Edit("Value : ", self._vars.get(existing, "") if existing else "")

        def save():
            n, v = name.edit_text.strip(), value.edit_text.strip()
            if not config.valid_name(n) or not config.valid_value(v):
                self.app.notify("Invalid name or value (e.g. EDITOR=nvim).", error=True)
                return
            updated = dict(self._vars)
            if existing and existing != n:
                updated.pop(existing, None)
            updated[n] = v
            self.app.pop()
            self._apply(updated)

        modal = Modal(
            self.app, "Edit variable" if existing else "Add variable",
            [urwid.Text(("hint", "A shell variable and value, e.g. EDITOR=nvim.")),
             urwid.Divider(), name, value],
            [("Save", save), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 72), height=("relative", 52))
