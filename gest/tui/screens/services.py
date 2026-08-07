"""Services module screen (OpenRC): list services, start/stop/restart, enable.

Keyboard: s start · x stop · r restart · e toggle enable · Esc back. Actions go
through the privileged backend (polkit action services.manage) and the list
refreshes afterward.
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from gest.core.services import reader as services_reader
from gest.core.services.backend_client import ServicesBackend


class ServicesScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("s", "start", "Start"),
        Binding("x", "stop", "Stop"),
        Binding("r", "restart", "Restart"),
        Binding("e", "toggle_enable", "Enable/Disable"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._services: dict = {}
        self._order: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Services (OpenRC)", id="use-title")
        yield Static(" s start · x stop · r restart · e enable/disable · Esc back", id="use-hint")
        table = DataTable(id="services", cursor_type="row", zebra_stripes=True)
        table.add_columns("Service", "Status", "Runlevels")
        yield table
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Services"
        self.query_one("#services", DataTable).focus()
        self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        services = services_reader.list_services()
        self.app.call_from_thread(self._populate, services)

    def _populate(self, services: list) -> None:
        table = self.query_one("#services", DataTable)
        prev = table.cursor_row
        table.clear()
        self._services = {}
        self._order = []
        for svc in services:
            self._services[svc.name] = svc
            self._order.append(svc.name)
            table.add_row(
                svc.name,
                "● started" if svc.running else svc.status,
                " ".join(svc.runlevels) or "—",
                key=svc.name,
            )
        if self._order:
            table.move_cursor(row=min(prev, len(self._order) - 1))

    def _current(self):
        if not self._order:
            return None
        return self._services[self._order[self.query_one("#services", DataTable).cursor_row]]

    def action_start(self) -> None:
        self._control("start")

    def action_stop(self) -> None:
        self._control("stop")

    def action_restart(self) -> None:
        self._control("restart")

    def action_toggle_enable(self) -> None:
        svc = self._current()
        if svc is not None:
            self._set_enabled(svc.name, not svc.enabled)

    def _control(self, action: str) -> None:
        svc = self._current()
        if svc is not None:
            self._run_control(svc.name, action)

    @work(exclusive=True)
    async def _run_control(self, name: str, action: str) -> None:
        backend = ServicesBackend()
        try:
            await backend.connect()
            ok, _out = await backend.control(name, action)
        except Exception as exc:
            self.app.notify(f"{name}: {exc}", severity="error")
            await backend.close()
            return
        await backend.close()
        self.app.notify(
            f"{name}: {action} {'ok' if ok else 'failed'}",
            severity="information" if ok else "error",
        )
        self.load()

    @work(exclusive=True)
    async def _set_enabled(self, name: str, enabled: bool) -> None:
        backend = ServicesBackend()
        try:
            await backend.connect()
            ok, _out = await backend.set_enabled(name, enabled)
        except Exception as exc:
            self.app.notify(f"{name}: {exc}", severity="error")
            await backend.close()
            return
        await backend.close()
        verb = "enabled" if enabled else "disabled"
        self.app.notify(
            f"{name}: {verb} {'ok' if ok else 'failed'}",
            severity="information" if ok else "error",
        )
        self.load()
