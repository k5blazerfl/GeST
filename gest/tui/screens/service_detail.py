"""Read-only detail for one OpenRC service.

Opened with Enter from the services list. Shows the init script's own
description plus its dependency graph (needs / uses / wants) and what depends on
it (needed-by) — the questions you'd otherwise answer with a handful of
`rc-service X ineed`/`needsme` invocations.
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from gest.core.services import reader as services_reader
from gest.core.services.model import Service, ServiceDetail


class ServiceDetailScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self, service: Service) -> None:
        super().__init__()
        self._svc = service

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._svc.name, id="detail-title")
        yield VerticalScroll(Static(" reading service metadata …", id="detail-body"))
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Service detail"
        self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        detail = services_reader.describe_service(
            self._svc.name,
            status=self._svc.status,
            runlevels=self._svc.runlevels,
        )
        self.app.call_from_thread(self._render, detail)

    def _render(self, d: ServiceDetail) -> None:
        lines: list[str] = []
        state = "[green]● started[/green]" if d.running else d.status
        lines.append(f"[b]Status[/b]     {state}")
        lines.append(f"[b]Runlevels[/b]  {' '.join(d.runlevels) or '—'}")
        if d.description:
            lines.append("")
            lines.append(d.description)

        def block(label: str, items: list[str]) -> None:
            lines.append("")
            lines.append(f"[b]{label}[/b]")
            if items:
                lines.extend(f"  • {name}" for name in items)
            else:
                lines.append("  —")

        block("Needs", d.needs)
        block("Uses", d.uses)
        block("Wants", d.wants)
        block("Needed by", d.needed_by)
        self.query_one("#detail-body", Static).update("\n".join(lines))
