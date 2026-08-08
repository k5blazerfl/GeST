"""Network module screen: list interfaces and bring them up/down.

Reading interface state is unprivileged (`ip -j addr`); toggling a link goes
through the polkit-gated Network backend (`ip link set`). Static/DHCP config
editing (netifrc) is intentionally out of scope for now.
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Checkbox, DataTable, Header, Input, Label, Static

from gest.core.network import netifrc, reader
from gest.core.network.backend_client import NetworkBackend
from gest.core.network.model import Interface
from gest.tui.widgets.bracket_button import BracketButton
from gest.tui.widgets.function_bar import FunctionBar


class InterfaceConfigScreen(ModalScreen):
    """Modal to set an interface to DHCP or a static address (netifrc)."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, iface: str, config: netifrc.InterfaceConfig) -> None:
        super().__init__()
        self._iface = iface
        self._config = config

    def compose(self) -> ComposeResult:
        static = self._config.method == "static"
        with Vertical(id="form"):
            yield Label(f"Configure {self._iface}", classes="form-title")
            yield Label(f"current: {self._config.method}")
            yield Checkbox("Use DHCP (uncheck for static)", value=not static, id="f-dhcp")
            yield Label("Static IP address (CIDR, e.g. 192.168.1.5/24)")
            yield Input(value=self._config.address if static else "", id="f-address")
            yield Label("Default gateway (optional)")
            yield Input(value=self._config.gateway if static else "", id="f-gateway")
            with Horizontal(classes="form-buttons"):
                yield BracketButton("Save", id="save")
                yield BracketButton("Cancel", id="cancel")

    def on_bracket_button_pressed(self, event: BracketButton.Pressed) -> None:
        if event.button.id != "save":
            self.dismiss(None)
            return
        if self.query_one("#f-dhcp", Checkbox).value:
            self.dismiss({"method": "dhcp", "address": "", "gateway": ""})
            return
        address = self.query_one("#f-address", Input).value.strip()
        gateway = self.query_one("#f-gateway", Input).value.strip()
        if not netifrc.valid_address(address):
            self.app.notify("Enter a valid CIDR address (e.g. 192.168.1.5/24).",
                            severity="error")
            return
        if not netifrc.valid_gateway(gateway):
            self.app.notify("Invalid gateway address.", severity="error")
            return
        self.dismiss({"method": "static", "address": address, "gateway": gateway})

    def action_cancel(self) -> None:
        self.dismiss(None)


class NetworkScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("f9", "app.pop_screen", "Back"),
        Binding("u", "link_up", "Up"),
        Binding("d", "link_down", "Down"),
        Binding("c", "configure", "Configure"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._ifaces: dict[str, Interface] = {}
        self._order: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Network interfaces", id="net-title")
        yield Static(
            " u up · d down · c configure (DHCP/static) · r refresh · Esc back",
            id="net-hint",
        )
        table = DataTable(id="net-table", cursor_type="row", zebra_stripes=True)
        table.add_columns("Interface", "State", "MAC", "Addresses")
        yield table
        yield FunctionBar(
            [("u", "Up"), ("d", "Down"), ("c", "Config"), ("r", "Refresh"), ("F9", "Back")]
        )

    def on_mount(self) -> None:
        self.title = "Network"
        self.query_one("#net-table", DataTable).focus()
        self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        self.app.call_from_thread(self._populate, reader.list_interfaces())

    def _populate(self, ifaces: list[Interface]) -> None:
        table = self.query_one("#net-table", DataTable)
        prev = table.cursor_row
        table.clear()
        self._ifaces = {i.name: i for i in ifaces}
        self._order = [i.name for i in ifaces]
        for i in ifaces:
            state = "● up" if i.up else i.state.lower()
            table.add_row(i.name, state, i.mac or "—", " ".join(i.addresses) or "—")
        if self._order:
            table.move_cursor(row=min(prev, len(self._order) - 1))

    def _current(self) -> str | None:
        table = self.query_one("#net-table", DataTable)
        if not self._order or table.cursor_row is None:
            return None
        if 0 <= table.cursor_row < len(self._order):
            return self._order[table.cursor_row]
        return None

    def action_refresh(self) -> None:
        self.load()

    def action_configure(self) -> None:
        name = self._current()
        if name is None:
            return
        if name == "lo":
            self.app.notify("The loopback interface isn't configurable.",
                            severity="warning")
            return
        config = reader.read_interface_config(name)
        self.app.push_screen(
            InterfaceConfigScreen(name, config),
            lambda data: self._on_config(name, data),
        )

    def _on_config(self, name: str, data) -> None:
        if not data:
            return
        self._run_config(name, data)

    @work(exclusive=True)
    async def _run_config(self, name: str, data) -> None:
        backend = NetworkBackend()
        try:
            await backend.connect()
            ok, out = await backend.set_interface_config(
                name, data["method"], data["address"], data["gateway"])
        except Exception as exc:
            self.app.notify(f"{name}: {exc}", severity="error")
            await backend.close()
            return
        await backend.close()
        self.app.notify(out or ("done" if ok else "failed"),
                        severity="information" if ok else "error")

    def action_link_up(self) -> None:
        self._set_link(True)

    def action_link_down(self) -> None:
        self._set_link(False)

    def _set_link(self, up: bool) -> None:
        name = self._current()
        if name is None:
            return
        if name == "lo":
            self.app.notify("The loopback interface can't be toggled.",
                            severity="warning")
            return
        self._run_set_link(name, up)

    @work(exclusive=True)
    async def _run_set_link(self, name: str, up: bool) -> None:
        backend = NetworkBackend()
        try:
            await backend.connect()
            ok, out = await backend.set_link(name, up)
        except Exception as exc:
            self.app.notify(f"{name}: {exc}", severity="error")
            await backend.close()
            return
        await backend.close()
        verb = "up" if up else "down"
        self.app.notify(
            out or f"{name} brought {verb}" if ok else f"{name}: failed to bring {verb}",
            severity="information" if ok else "error",
        )
        self.load()
