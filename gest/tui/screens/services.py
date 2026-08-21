"""Services module in urwid: list + start/stop/restart/enable/mask + detail.

Reads are unprivileged (``systemctl`` or ``rc-service`` list/show, chosen by the
running init); mutations go through the async ServicesBackend over D-Bus — this
is the first ported module that proves the async mutation path on urwid's
asyncio loop.
"""

from __future__ import annotations

import urwid

from gest.core import init
from gest.core.services import dispatch
from gest.core.services.backend_client import ServicesBackend
from gest.core.services.model import Service
from gest.tui.runtime import App, Screen, boxed


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


def _enabled_label(svc: Service) -> str:
    """One-word install state for the list column."""
    return svc.enabled_state or "—"


class ServicesScreen(Screen):
    def __init__(self, app: App) -> None:
        self._services: dict[str, Service] = {}
        self._order: list[str] = []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, boxed(self._list, title="Services"),
            title="Services",
            footer_keys=[
                ("Enter", "Detail"), ("s", "Start"), ("x", "Stop"),
                ("r", "Restart"), ("e", "Enable"), ("m", "Mask"),
                ("Esc", "Back"),
            ],
            help_text=(
                ("OpenRC services on this system.\n\n"
                 "Each row shows the service, its run state, and whether it is\n"
                 "enabled (added to a runlevel).\n\n"
                 "Enter  service detail (dependencies / runlevels)\n"
                 "s / x / r   start / stop / restart\n"
                 "e      enable / disable at boot (rc-update add/del)\n"
                 "m      mask (not supported on OpenRC)\n"
                 "Esc    back")
                if init.is_openrc() else
                ("systemd service units on this system.\n\n"
                 "Each row shows the unit, its active state, and its install state\n"
                 "(enabled / disabled / static / masked …).\n\n"
                 "Enter  service detail (dependencies)\n"
                 "s / x / r   start / stop / restart\n"
                 "e      enable / disable at boot (systemctl enable/disable)\n"
                 "m      mask / unmask (systemctl mask/unmask)\n"
                 "Esc    back")
            ),
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        services = await self.app.run_blocking(dispatch.list_services)
        self._services = {s.name: s for s in services}
        self._order = [s.name for s in services]
        rows = [
            _row(f"{s.name:<32} {('● active' if s.running else s.status):<12} "
                 f"{_enabled_label(s)}")
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

    async def _set_masked(self, name: str, masked: bool) -> None:
        backend = ServicesBackend()
        try:
            await backend.connect()
            ok, _out = await backend.set_masked(name, masked)
        except Exception as exc:
            self.app.notify(f"{name}: {exc}", error=True)
            await backend.close()
            return
        await backend.close()
        verb = "masked" if masked else "unmasked"
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
        elif key in ("m", "M"):
            self.app.run_async(self._set_masked(svc.name, not svc.masked))
        else:
            return key
        return None


class ServiceDetailScreen(Screen):
    def __init__(self, app: App, service: Service) -> None:
        self._svc = service
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" reading …")])
        body = urwid.ListBox(self._walker)
        super().__init__(
            app, boxed(body, title=service.name),
            title=f"Service · {service.name}",
            footer_keys=[("m", "Mask"), ("Esc", "Back")],
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        detail = await self.app.run_blocking(
            lambda: dispatch.describe_service(
                self._svc.name, status=self._svc.status,
                sub_state=self._svc.sub_state, enabled_state=self._svc.enabled_state,
                runlevels=self._svc.runlevels,
            )
        )
        sub = f" ({detail.sub_state})" if detail.sub_state else ""
        lines = [
            f"Status:  {'● active' if detail.running else detail.status}{sub}",
            f"Enabled: {detail.enabled_state or '—'}",
        ]
        if detail.runlevels:
            lines.append(f"Runlevels: {', '.join(detail.runlevels)}")
        if detail.load_state:
            lines.append(f"Loaded:  {detail.load_state}")
        if detail.description:
            lines += ["", detail.description]

        def block(label: str, items: list[str]) -> None:
            lines.append("")
            lines.append(f"{label}:")
            lines.extend(f"  • {name}" for name in items) if items else lines.append("  —")

        block("Requires", detail.requires)
        block("Wants", detail.wants)
        block("After", detail.after)
        block("Required by", detail.required_by)
        self._walker[:] = [urwid.SelectableIcon(line, 0) for line in lines]
        self._walker.set_focus(0)
        self.app.refresh()

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key in ("m", "M"):
            self.app.run_async(self._toggle_masked())
            return None
        return key

    async def _toggle_masked(self) -> None:
        masked = not self._svc.masked
        backend = ServicesBackend()
        try:
            await backend.connect()
            ok, _out = await backend.set_masked(self._svc.name, masked)
        except Exception as exc:
            self.app.notify(f"{self._svc.name}: {exc}", error=True)
            await backend.close()
            return
        await backend.close()
        verb = "masked" if masked else "unmasked"
        self.app.notify(f"{self._svc.name}: {verb} {'ok' if ok else 'failed'}", error=not ok)
        if ok:
            self._svc.enabled_state = "masked" if masked else "disabled"
            await self._load()
