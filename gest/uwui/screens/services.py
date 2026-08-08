"""Services module (OpenRC) in urwid: list + start/stop/restart/enable + detail.

Reads are unprivileged (rc-service/rc-update/rc-status); mutations go through the
async ServicesBackend over D-Bus — this is the first ported module that proves
the async mutation path on urwid's asyncio loop.
"""

from __future__ import annotations

import urwid

from gest.core.services import reader
from gest.core.services.backend_client import ServicesBackend
from gest.core.services.model import Service
from gest.uwui.runtime import App, Screen


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


class ServicesScreen(Screen):
    def __init__(self, app: App) -> None:
        self._services: dict[str, Service] = {}
        self._order: list[str] = []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, urwid.LineBox(self._list, title="Services (OpenRC)"),
            title="Services",
            footer_keys=[
                ("Enter", "Detail"), ("s", "Start"), ("x", "Stop"),
                ("r", "Restart"), ("e", "Enable"), ("Esc", "Back"),
            ],
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        services = await self.app.run_blocking(reader.list_services)
        self._services = {s.name: s for s in services}
        self._order = [s.name for s in services]
        rows = [
            _row(f"{s.name:<26} {('● started' if s.running else s.status):<12} "
                 f"{' '.join(s.runlevels) or '—'}")
            for s in services
        ] or [urwid.Text(" (no services)")]
        prev = self._walker.focus if self._walker else 0
        self._walker[:] = rows
        if self._order:
            self._walker.set_focus(min(prev or 0, len(self._order) - 1))
        self.app.refresh()

    def _current(self) -> Service | None:
        if not self._order:
            return None
        return self._services[self._order[self._walker.focus]]

    async def _control(self, name: str, action: str) -> None:
        backend = ServicesBackend()
        try:
            await backend.connect()
            ok, _out = await backend.control(name, action)
        except Exception as exc:
            self.app.notify(f"{name}: {exc}", error=True)
            await backend.close()
            return
        await backend.close()
        self.app.notify(f"{name}: {action} {'ok' if ok else 'failed'}", error=not ok)
        await self._load()

    async def _set_enabled(self, name: str, enabled: bool) -> None:
        backend = ServicesBackend()
        try:
            await backend.connect()
            ok, _out = await backend.set_enabled(name, enabled)
        except Exception as exc:
            self.app.notify(f"{name}: {exc}", error=True)
            await backend.close()
            return
        await backend.close()
        verb = "enabled" if enabled else "disabled"
        self.app.notify(f"{name}: {verb} {'ok' if ok else 'failed'}", error=not ok)
        await self._load()

    def handle_key(self, key):
        svc = self._current()
        if key == "esc":
            self.app.pop()
            return None
        if svc is None:
            return key
        if key == "enter":
            self.app.push(ServiceDetailScreen(self.app, svc))
        elif key == "s":
            self.app.run_async(self._control(svc.name, "start"))
        elif key == "x":
            self.app.run_async(self._control(svc.name, "stop"))
        elif key == "r":
            self.app.run_async(self._control(svc.name, "restart"))
        elif key == "e":
            self.app.run_async(self._set_enabled(svc.name, not svc.enabled))
        else:
            return key
        return None


class ServiceDetailScreen(Screen):
    def __init__(self, app: App, service: Service) -> None:
        self._svc = service
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" reading …")])
        body = urwid.ListBox(self._walker)
        super().__init__(
            app, urwid.LineBox(body, title=service.name),
            title=f"Service · {service.name}",
            footer_keys=[("Esc", "Back")],
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        detail = await self.app.run_blocking(
            lambda: reader.describe_service(
                self._svc.name, status=self._svc.status, runlevels=self._svc.runlevels
            )
        )
        lines = [
            f"Status:    {'● started' if detail.running else detail.status}",
            f"Runlevels: {' '.join(detail.runlevels) or '—'}",
        ]
        if detail.description:
            lines += ["", detail.description]

        def block(label: str, items: list[str]) -> None:
            lines.append("")
            lines.append(f"{label}:")
            lines.extend(f"  • {name}" for name in items) if items else lines.append("  —")

        block("Needs", detail.needs)
        block("Uses", detail.uses)
        block("Wants", detail.wants)
        block("Needed by", detail.needed_by)
        self._walker[:] = [urwid.SelectableIcon(line, 0) for line in lines]
        self._walker.set_focus(0)
        self.app.refresh()

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        return key
