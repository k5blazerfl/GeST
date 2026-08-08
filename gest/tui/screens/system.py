"""System settings screens: hostname, timezone and locale.

Each reads the current value unprivileged and applies changes through the
polkit-gated System backend.
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Header, Input, OptionList, Static
from textual.widgets.option_list import Option

from gest.core.system import hostname as hostname_core
from gest.core.system import locale as locale_core
from gest.core.system import timezone as timezone_core
from gest.core.system.backend_client import SystemBackend
from gest.tui.widgets.bracket_button import BracketButton
from gest.tui.widgets.function_bar import FunctionBar


class _SystemApplyMixin:
    """Shared 'apply via backend, notify, go back' helper."""

    @work(exclusive=True)
    async def _apply(self, action, success_pop: bool = True) -> None:
        backend = SystemBackend()
        try:
            await backend.connect()
            ok, out = await action(backend)
        except Exception as exc:
            self.app.notify(f"{exc}", severity="error")
            await backend.close()
            return
        await backend.close()
        self.app.notify(out or ("done" if ok else "failed"),
                        severity="information" if ok else "error")
        if ok and success_pop:
            self.app.pop_screen()


class HostnameScreen(Screen, _SystemApplyMixin):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("f9", "app.pop_screen", "Back"),
        Binding("f10", "apply", "Apply"),
        Binding("q", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Hostname", id="sys-title")
        yield Static("", id="sys-current")
        yield Input(id="hostname-input")
        with Horizontal(id="sys-buttons"):
            yield BracketButton("Apply", id="apply")
            yield BracketButton("Cancel", id="cancel")
        yield FunctionBar([("F10", "Apply"), ("F9", "Back")])

    def on_mount(self) -> None:
        self.title = "System · Hostname"
        current = hostname_core.current_hostname()
        self.query_one("#sys-current", Static).update(f" current: {current}")
        inp = self.query_one("#hostname-input", Input)
        inp.value = current
        inp.focus()

    def on_bracket_button_pressed(self, event: BracketButton.Pressed) -> None:
        if event.button.id == "apply":
            self.action_apply()
        else:
            self.app.pop_screen()

    def action_apply(self) -> None:
        name = self.query_one("#hostname-input", Input).value.strip()
        if not hostname_core.valid_hostname(name):
            self.app.notify("Invalid hostname.", severity="error")
            return
        self._apply(lambda b: b.set_hostname(name))


class _ChoiceScreen(Screen, _SystemApplyMixin):
    """A filterable list-of-choices screen for timezone/locale."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("f9", "app.pop_screen", "Back"),
        Binding("f10", "apply", "Apply"),
        Binding("/", "focus_filter", "Filter"),
        Binding("q", "app.quit", "Quit"),
    ]

    _TITLE = ""
    _FILTERABLE = True

    def __init__(self) -> None:
        super().__init__()
        self._all: list[str] = []
        self._current: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._TITLE, id="sys-title")
        yield Static("", id="sys-current")
        if self._FILTERABLE:
            yield Input(placeholder="filter…", id="choice-filter")
        yield OptionList(id="choice-list")
        with Horizontal(id="sys-buttons"):
            yield BracketButton("Apply", id="apply")
            yield BracketButton("Cancel", id="cancel")
        yield FunctionBar([("F10", "Apply"), ("/", "Filter"), ("F9", "Back")])

    def on_mount(self) -> None:
        self.title = f"System · {self._TITLE}"
        self.load()

    # subclasses provide these
    def _load_choices(self) -> tuple[list[str], str]:
        raise NotImplementedError

    def _do_set(self, backend, value):
        raise NotImplementedError

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        choices, current = self._load_choices()
        self.app.call_from_thread(self._populate, choices, current)

    def _populate(self, choices: list[str], current: str) -> None:
        self._all = choices
        self._current = current
        self.query_one("#sys-current", Static).update(f" current: {current or '—'}")
        self._fill(choices, current)

    def _fill(self, choices: list[str], highlight: str = "") -> None:
        ol = self.query_one("#choice-list", OptionList)
        ol.clear_options()
        for value in choices:
            ol.add_option(Option(value, id=value))
        if highlight and highlight in choices:
            ol.highlighted = choices.index(highlight)
        elif choices:
            ol.highlighted = 0

    def action_focus_filter(self) -> None:
        if self._FILTERABLE:
            self.query_one("#choice-filter", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        needle = event.value.strip().lower()
        self._fill([c for c in self._all if needle in c.lower()], self._current)

    def on_bracket_button_pressed(self, event: BracketButton.Pressed) -> None:
        if event.button.id == "apply":
            self.action_apply()
        else:
            self.app.pop_screen()

    def action_apply(self) -> None:
        ol = self.query_one("#choice-list", OptionList)
        if ol.highlighted is None:
            return
        value = ol.get_option_at_index(ol.highlighted).id
        self._apply(lambda b: self._do_set(b, value))


class TimezoneScreen(_ChoiceScreen):
    _TITLE = "Timezone"

    def _load_choices(self):
        return timezone_core.list_zones(), timezone_core.current_timezone()

    def _do_set(self, backend, value):
        return backend.set_timezone(value)


class LocaleScreen(_ChoiceScreen):
    _TITLE = "Locale"

    def _load_choices(self):
        return locale_core.list_locales(), locale_core.current_locale()

    def _do_set(self, backend, value):
        return backend.set_locale(value)
