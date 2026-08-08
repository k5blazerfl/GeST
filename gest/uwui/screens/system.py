"""System settings in urwid: hostname, timezone, locale.

Reads are unprivileged; applying goes through the async SystemBackend.
"""

from __future__ import annotations

import urwid

from gest.core.system import hostname as hostname_core
from gest.core.system import locale as locale_core
from gest.core.system import timezone as timezone_core
from gest.core.system.backend_client import SystemBackend
from gest.uwui.runtime import App, Screen


def _choice(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


async def _apply(app: App, coro_factory, *, on_ok_pop: bool = True) -> None:
    backend = SystemBackend()
    try:
        await backend.connect()
        ok, out = await coro_factory(backend)
    except Exception as exc:
        app.notify(str(exc), error=True)
        await backend.close()
        return
    await backend.close()
    app.notify(out or ("done" if ok else "failed"), error=not ok)
    if ok and on_ok_pop:
        app.pop()


class HostnameScreen(Screen):
    def __init__(self, app: App) -> None:
        current = hostname_core.current_hostname()
        self._edit = urwid.Edit("Hostname: ", current)
        body = urwid.Filler(
            urwid.Pile([
                urwid.Text(f"Current: {current}"),
                urwid.Divider(),
                self._edit,
                urwid.Divider(),
                urwid.Text("Enter or F10 to apply · Esc to go back."),
            ]),
            valign="top",
        )
        super().__init__(
            app, urwid.LineBox(body, title="Hostname"), title="System · Hostname",
            footer_keys=[("Enter", "Apply"), ("Esc", "Back")],
        )

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key in ("enter", "f10"):
            name = self._edit.edit_text.strip()
            if not hostname_core.valid_hostname(name):
                self.app.notify("Invalid hostname.", error=True)
                return None
            self.app.run_async(_apply(self.app, lambda b: b.set_hostname(name)))
            return None
        return key


class _ChoiceScreen(Screen):
    """A filterable list of choices; Enter on a choice applies it."""

    _TITLE = ""

    def __init__(self, app: App) -> None:
        self._all: list[str] = []
        self._current = ""
        self._filter = urwid.Edit("Filter: ")
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        self._current_text = urwid.Text("")
        body = urwid.Pile([
            ("pack", self._current_text),
            ("pack", self._filter),
            ("weight", 1, urwid.LineBox(self._list, title=self._TITLE)),
        ])
        super().__init__(
            app, body, title=f"System · {self._TITLE}",
            footer_keys=[("Enter", "Apply"), ("↑↓", "Select"), ("Esc", "Back")],
        )
        urwid.connect_signal(self._filter, "change", self._on_filter)
        app.run_async(self._load())

    # subclasses implement these
    def _load_choices(self) -> tuple[list[str], str]:
        raise NotImplementedError

    def _set(self, backend, value):
        raise NotImplementedError

    async def _load(self) -> None:
        choices, current = await self.app.run_blocking(self._load_choices)
        self._all = choices
        self._current = current
        self._current_text.set_text(f" Current: {current or '—'}")
        self._fill(choices)

    def _fill(self, choices: list[str]) -> None:
        rows = [_choice(c) for c in choices] or [urwid.Text(" (no matches)")]
        self._walker[:] = rows
        if choices and self._current in choices:
            self._walker.set_focus(choices.index(self._current))
        elif choices:
            self._walker.set_focus(0)
        self._visible = choices
        self.app.refresh()

    def _on_filter(self, _edit, text) -> None:
        needle = text.strip().lower()
        self._fill([c for c in self._all if needle in c.lower()])

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key == "enter" and getattr(self, "_visible", None):
            value = self._visible[self._walker.focus]
            self.app.run_async(_apply(self.app, lambda b: self._set(b, value)))
            return None
        return key


class TimezoneScreen(_ChoiceScreen):
    _TITLE = "Timezone"

    def _load_choices(self):
        return timezone_core.list_zones(), timezone_core.current_timezone()

    def _set(self, backend, value):
        return backend.set_timezone(value)


class LocaleScreen(_ChoiceScreen):
    _TITLE = "Locale"

    def _load_choices(self):
        return locale_core.list_locales(), locale_core.current_locale()

    def _set(self, backend, value):
        return backend.set_locale(value)
