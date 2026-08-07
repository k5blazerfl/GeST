"""USE-flag editor: toggle per-package flags (tri-state) and write package.use.

Each flag is default / on / off. Space cycles the highlighted flag; `a` applies.
Applying shows the exact package.use line to be written and, on confirm, hands
it to the privileged backend (polkit action modify-config).
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.coordinate import Coordinate
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Header, Static

from gest.core.software import useflags
from gest.core.software.backend_client import SoftwareBackend
from gest.tui.screens.install import InstallScreen

_LABEL = {useflags.DEFAULT: "default", useflags.ON: "+ on", useflags.OFF: "- off"}
_NEXT = {useflags.DEFAULT: useflags.ON, useflags.ON: useflags.OFF, useflags.OFF: useflags.DEFAULT}


class ConfirmWriteScreen(ModalScreen[bool]):
    """Confirm the package.use change; returns True to write."""

    BINDINGS = [
        Binding("y,enter", "confirm", "Write"),
        Binding("n,escape", "cancel", "Cancel"),
    ]

    def __init__(self, cp: str, line: str) -> None:
        super().__init__()
        self._cp = cp
        self._line = line

    def compose(self) -> ComposeResult:
        with Horizontal(id="confirm-box"):
            body = self._line if self._line else f"(remove all GeST pins for {self._cp})"
            yield Static(
                f"Write to /etc/portage/package.use/gest:\n\n  {body}\n\n"
                "You'll be offered a rebuild next to apply it.",
                id="confirm-text",
            )
        with Horizontal(id="confirm-buttons"):
            yield Button("Write", id="ok", variant="success")
            yield Button("Cancel", id="no", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "ok")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class UseFlagScreen(Screen):
    """Edit the USE flags of a single package."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("space", "cycle", "Cycle flag"),
        Binding("a", "apply", "Apply"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self, cp: str) -> None:
        super().__init__()
        self.cp = cp
        self._states: dict[str, str] = {}
        self._order: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"USE flags — {self.cp}", id="use-title")
        yield Static(" Space cycles default → on → off · a to apply · Esc back", id="use-hint")
        table = DataTable(id="flags", cursor_type="row", zebra_stripes=True)
        table.add_columns("Pin", "Flag", "Now", "Description")
        yield table
        yield Footer()

    def on_mount(self) -> None:
        self.title = "USE flags"
        self.query_one("#flags", DataTable).focus()
        self.load_flags()

    @work(thread=True, exclusive=True)
    def load_flags(self) -> None:
        rows = useflags.flags_for(self.cp)
        self.app.call_from_thread(self._populate, rows)

    def _populate(self, rows: list[useflags.FlagRow]) -> None:
        table = self.query_one("#flags", DataTable)
        table.clear()
        self._states = {}
        self._order = []
        for r in rows:
            self._states[r.name] = r.state
            self._order.append(r.name)
            table.add_row(
                _LABEL[r.state],
                r.name,
                "on" if r.effective else "off",
                (r.description or "")[:60],
                key=r.name,
            )
        if not rows:
            self.query_one("#use-hint", Static).update(" this package exposes no USE flags")

    def action_cycle(self) -> None:
        table = self.query_one("#flags", DataTable)
        if not self._order:
            return
        flag = self._order[table.cursor_row]
        self._states[flag] = _NEXT[self._states[flag]]
        table.update_cell_at(Coordinate(table.cursor_row, 0), _LABEL[self._states[flag]])

    def action_apply(self) -> None:
        line = useflags.build_line(self.cp, self._states)
        old, new = useflags.preview(self.cp, self._states)
        if new == old:
            self.app.notify("No USE-flag changes to apply.", severity="information")
            return
        self.app.push_screen(ConfirmWriteScreen(self.cp, line), self._on_confirm)

    def _on_confirm(self, confirmed: bool | None) -> None:
        if confirmed:
            self._write(useflags.build_line(self.cp, self._states))

    @work(exclusive=True)
    async def _write(self, line: str) -> None:
        backend = SoftwareBackend()
        try:
            await backend.connect()
            await backend.set_package_use(self.cp, line)
        except Exception as exc:  # noqa: BLE001 - report any failure to the user
            self.app.notify(f"Could not write package.use: {exc}", severity="error")
            await backend.close()
            return
        await backend.close()
        self.app.notify(
            f"Wrote package.use for {self.cp}.", severity="information"
        )
        # Close the loop: hand off to a rebuild preview so the flag change
        # actually takes effect (emerge --changed-use). Esc there skips it.
        self.app.pop_screen()
        self.app.push_screen(InstallScreen(self.cp, rebuild=True))
