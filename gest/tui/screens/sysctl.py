"""Kernel parameters (sysctl) in urwid: edit the GeST /etc/sysctl.d drop-in.

Reads the managed drop-in unprivileged; applying goes through the polkit-gated
SysctlBackend, which writes the drop-in and loads it with `sysctl -p`.
"""

from __future__ import annotations

import contextlib

import urwid

from gest.core.sysctl import config, reader
from gest.core.sysctl.backend_client import SysctlBackend
from gest.tui.runtime import App, Modal, Screen, boxed


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


class SysctlScreen(Screen):
    def __init__(self, app: App) -> None:
        self._settings: dict[str, str] = {}
        self._keys: list[str] = []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, boxed(self._list, title="/etc/sysctl.d/10-gest.conf"),
            title="Kernel Parameters (sysctl)",
            footer_keys=[("a", "Add"), ("e", "Edit"), ("d", "Remove"), ("Esc", "Back")],
        )
        self._load()

    def _load(self) -> None:
        self._settings = reader.current_settings()
        self._keys = sorted(self._settings)
        rows = [_row(f"{k} = {self._settings[k]}") for k in self._keys] or \
            [urwid.Text(" (no GeST-managed parameters)")]
        self._walker[:] = rows
        if self._keys:
            self._walker.set_focus(min(self._walker.focus or 0, len(self._keys) - 1))
        self.app.refresh()

    def _current(self) -> str | None:
        if not self._keys:
            return None
        idx = self._walker.focus
        return self._keys[idx] if idx is not None and 0 <= idx < len(self._keys) else None

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
            updated = {k: v for k, v in self._settings.items() if k != cur}
            self._apply(updated)
            return None
        return key

    def _apply(self, settings: dict[str, str]) -> None:
        self.app.run_async(self._call(settings))

    async def _call(self, settings: dict[str, str]) -> None:
        backend = SysctlBackend()
        try:
            await backend.connect()
            ok, out = await backend.apply_settings(settings)
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
        key = urwid.Edit("Key   : ", existing or "")
        value = urwid.Edit("Value : ", self._settings.get(existing, "") if existing else "")

        def save():
            k, v = key.edit_text.strip(), value.edit_text.strip()
            if not config.valid_key(k) or not config.valid_value(v):
                self.app.notify("Invalid key or value (e.g. net.ipv4.ip_forward = 1).",
                                error=True)
                return
            updated = dict(self._settings)
            if existing and existing != k:
                updated.pop(existing, None)
            updated[k] = v
            self.app.pop()
            self._apply(updated)

        modal = Modal(
            self.app, "Edit parameter" if existing else "Add parameter",
            [urwid.Text(("hint", "A sysctl key and value, e.g. vm.swappiness = 10.")),
             urwid.Divider(), key, value],
            [("Save", save), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 72), height=("relative", 52))
