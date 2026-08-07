"""Keyword-acceptance and mask editor for a single package.

Two tri-state rows — keyword acceptance and mask state. Space cycles the
highlighted row; `a` applies. Writes go to package.accept_keywords / package.mask
/ package.unmask via the backend (polkit modify-config).
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.coordinate import Coordinate
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Header, Static

from gest.core.software import pkgconfig as pc
from gest.core.software.backend_client import SoftwareBackend

_KW_CYCLE = [pc.KW_DEFAULT, pc.KW_TESTING, pc.KW_ANY]
_MASK_CYCLE = [pc.MASK_DEFAULT, pc.MASKED, pc.UNMASKED]


def _kw_label(state: str) -> str:
    return {
        pc.KW_DEFAULT: "default (stable only)",
        pc.KW_TESTING: f"~{pc.arch()} (accept testing)",
        pc.KW_ANY: "** (accept any keyword)",
    }[state]


def _mask_label(state: str) -> str:
    return {
        pc.MASK_DEFAULT: "default",
        pc.MASKED: "masked",
        pc.UNMASKED: "unmasked (force-unmask)",
    }[state]


class _ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [
        Binding("y,enter", "confirm", "Write"),
        Binding("n,escape", "cancel", "Cancel"),
    ]

    def __init__(self, body: str) -> None:
        super().__init__()
        self._body = body

    def compose(self) -> ComposeResult:
        with Horizontal(id="confirm-box"):
            yield Static(self._body, id="confirm-text")
        with Horizontal(id="confirm-buttons"):
            yield Button("Write", id="ok", variant="success")
            yield Button("Cancel", id="no", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "ok")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class KeywordsScreen(Screen):
    """Edit keyword acceptance and mask state for a package."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("space", "cycle", "Cycle"),
        Binding("a", "apply", "Apply"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self, cp: str) -> None:
        super().__init__()
        self.cp = cp
        self._kw = pc.KW_DEFAULT
        self._mask = pc.MASK_DEFAULT

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"Keywords & mask — {self.cp}", id="use-title")
        yield Static(" Space cycles the highlighted setting · a to apply · Esc back", id="use-hint")
        table = DataTable(id="settings", cursor_type="row", zebra_stripes=True)
        table.add_columns("Setting", "Value")
        yield table
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Keywords & mask"
        self.query_one("#settings", DataTable).focus()
        self.load_state()

    @work(thread=True, exclusive=True)
    def load_state(self) -> None:
        kw = pc.keyword_state(self.cp)
        mask = pc.mask_state(self.cp)
        self.app.call_from_thread(self._populate, kw, mask)

    def _populate(self, kw: str, mask: str) -> None:
        self._kw, self._mask = kw, mask
        table = self.query_one("#settings", DataTable)
        table.clear()
        table.add_row("Keyword acceptance", _kw_label(kw), key="keyword")
        table.add_row("Mask state", _mask_label(mask), key="mask")

    def action_cycle(self) -> None:
        table = self.query_one("#settings", DataTable)
        row = table.cursor_row
        if row == 0:
            self._kw = _KW_CYCLE[(_KW_CYCLE.index(self._kw) + 1) % len(_KW_CYCLE)]
            table.update_cell_at(Coordinate(0, 1), _kw_label(self._kw))
        else:
            self._mask = _MASK_CYCLE[(_MASK_CYCLE.index(self._mask) + 1) % len(_MASK_CYCLE)]
            table.update_cell_at(Coordinate(1, 1), _mask_label(self._mask))

    def action_apply(self) -> None:
        writes = pc.changed_writes(self.cp, self._kw, self._mask)
        if not writes:
            self.app.notify("No keyword/mask changes to apply.", severity="information")
            return
        body = "Write:\n\n" + "\n".join(
            f"  package.{kind}: {line or '(clear entry)'}" for kind, line in writes
        )
        self.app.push_screen(_ConfirmScreen(body), lambda ok: self._on_confirm(ok, writes))

    def _on_confirm(self, confirmed: bool | None, writes: list[tuple[str, str]]) -> None:
        if confirmed:
            self._apply(writes)

    @work(exclusive=True)
    async def _apply(self, writes: list[tuple[str, str]]) -> None:
        backend = SoftwareBackend()
        try:
            await backend.connect()
            for kind, line in writes:
                await backend.set_package_config(kind, self.cp, line)
        except Exception as exc:  # noqa: BLE001 - report any failure
            self.app.notify(f"Could not write config: {exc}", severity="error")
            await backend.close()
            return
        await backend.close()
        self.app.notify(f"Updated keywords/mask for {self.cp}.", severity="information")
        self.app.pop_screen()
