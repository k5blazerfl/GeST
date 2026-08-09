"""Per-package configuration editors (urwid): USE flags and keyword/mask.

USE flags are tri-state (default/on/off) and applied via a --changed-use
rebuild; keyword/mask edits are written to /etc/portage/package.* through the
Portage backend (WriteConfig → portage.configure). Reached with u/k from
Software Management.
"""

from __future__ import annotations

import urwid

from gest.core.portage.backend_client import PortageBackend
from gest.core.software import pkgconfig as pc
from gest.core.software import useflags
from gest.tui.runtime import App, Screen
from gest.tui.screens.apply import ApplyScreen, rebuild_plan

_USE_NEXT = {useflags.DEFAULT: useflags.ON, useflags.ON: useflags.OFF,
             useflags.OFF: useflags.DEFAULT}
_USE_LABEL = {useflags.DEFAULT: "[default]", useflags.ON: "[  on   ]",
              useflags.OFF: "[  off  ]"}

_KW = [pc.KW_DEFAULT, pc.KW_TESTING, pc.KW_ANY]
_MASK = [pc.MASK_DEFAULT, pc.MASKED, pc.UNMASKED]


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


def _cycle(options: list[str], current: str) -> str:
    i = options.index(current) if current in options else 0
    return options[(i + 1) % len(options)]


class UseFlagScreen(Screen):
    def __init__(self, app: App, cp: str) -> None:
        self.cp = cp
        self._flags: list[str] = []
        self._states: dict[str, str] = {}
        self._descs: dict[str, str] = {}
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, urwid.LineBox(self._list, title=f"USE flags — {cp}"),
            title=f"USE · {cp}",
            footer_keys=[("Space", "Cycle"), ("a/F10", "Apply"), ("Esc", "Back")],
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        rows = await self.app.run_blocking(useflags.flags_for, self.cp)
        self._flags = [r.name for r in rows]
        self._states = {r.name: r.state for r in rows}
        self._descs = {r.name: r.description for r in rows}
        self._walker[:] = [_row(self._text(n)) for n in self._flags] or \
            [urwid.Text(" (no USE flags)")]
        if self._flags:
            self._walker.set_focus(0)
        self.app.refresh()

    def _text(self, name: str) -> str:
        return f"{_USE_LABEL[self._states[name]]} {name:<24} {self._descs.get(name, '')[:44]}"

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key == " " and self._flags:
            i = self._walker.focus
            name = self._flags[i]
            self._states[name] = _USE_NEXT[self._states[name]]
            self._walker[i].base_widget.set_text(self._text(name))
            self.app.refresh()
            return None
        if key in ("a", "f10"):
            self.app.run_async(self._apply())
            return None
        return key

    async def _apply(self) -> None:
        write = await self.app.run_blocking(
            lambda: useflags.write_for(self.cp, self._states))
        backend = PortageBackend()
        try:
            await backend.connect()
            await backend.write_config([write])
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        self.app.pop()  # close the editor, then apply via a --changed-use rebuild
        self.app.push(ApplyScreen(self.app, [rebuild_plan(self.cp)], verb="Rebuild"))


class KeywordsScreen(Screen):
    def __init__(self, app: App, cp: str) -> None:
        self.cp = cp
        self._kw = pc.keyword_state(cp)
        self._mask = pc.mask_state(cp)
        self._walker = urwid.SimpleFocusListWalker([])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, urwid.LineBox(self._list, title=f"Keywords / mask — {cp}"),
            title=f"Keywords · {cp}",
            footer_keys=[("Space", "Cycle"), ("a/F10", "Apply"), ("Esc", "Back")],
        )
        self._render()

    def _render(self) -> None:
        focus = self._walker.focus if self._walker else 0
        self._walker[:] = [
            _row(f"Keyword acceptance : {self._kw}"),
            _row(f"Mask               : {self._mask}"),
        ]
        self._walker.set_focus(min(focus, 1))

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key == " ":
            if self._walker.focus == 0:
                self._kw = _cycle(_KW, self._kw)
            else:
                self._mask = _cycle(_MASK, self._mask)
            self._render()
            return None
        if key in ("a", "f10"):
            self.app.run_async(self._apply())
            return None
        return key

    async def _apply(self) -> None:
        writes = await self.app.run_blocking(
            lambda: pc.writes_for(self.cp, self._kw, self._mask))
        if not writes:
            self.app.notify("No keyword/mask changes to apply.")
            return
        backend = PortageBackend()
        try:
            await backend.connect()
            await backend.write_config(writes)
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        self.app.notify("keyword/mask applied")
        self.app.pop()
