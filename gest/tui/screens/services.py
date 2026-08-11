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
from gest.tui.runtime import App, Screen, boxed


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


# What each OpenRC runlevel is for — shown beside the toggle so the choice is
# self-explanatory (rc-update itself gives no hint).
_RUNLEVEL_DESC = {
    "sysinit": "earliest — before boot",
    "boot": "one-time system boot",
    "default": "normal multi-user (most services)",
    "nonetwork": "default, but without networking",
    "shutdown": "run on shutdown",
}


class ServicesScreen(Screen):
    def __init__(self, app: App) -> None:
        self._services: dict[str, Service] = {}
        self._order: list[str] = []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, boxed(self._list, title="Services (OpenRC)"),
            title="Services",
            footer_keys=[
                ("Enter", "Detail"), ("s", "Start"), ("x", "Stop"),
                ("r", "Restart"), ("e", "Enable"), ("l", "Runlevels"),
                ("Esc", "Back"),
            ],
            help_text=(
                "OpenRC services on this system.\n\n"
                "Each row shows the service, its run status, and the runlevels it\n"
                "is enabled in (— means none).\n\n"
                "Enter  service detail (dependencies)\n"
                "s / x / r   start / stop / restart\n"
                "e      enable / disable in the default runlevel (quick toggle)\n"
                "l      manage which runlevels it starts in (boot, default, …)\n"
                "Esc    back"
            ),
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
        elif key in ("l", "L"):
            self._open_runlevels(svc)
        else:
            return key
        return None

    def _open_runlevels(self, svc: Service) -> None:
        # Reload the list when a runlevel changes so the row (behind this screen)
        # reflects the new runlevel set the moment the user pops back.
        self.app.push(ServiceRunlevelsScreen(
            self.app, svc, on_change=lambda: self.app.run_async(self._load())))


class ServiceDetailScreen(Screen):
    def __init__(self, app: App, service: Service) -> None:
        self._svc = service
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" reading …")])
        body = urwid.ListBox(self._walker)
        super().__init__(
            app, boxed(body, title=service.name),
            title=f"Service · {service.name}",
            footer_keys=[("l", "Runlevels"), ("Esc", "Back")],
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
        if key in ("l", "L"):
            # Manage runlevels; refresh this detail when they change.
            self.app.push(ServiceRunlevelsScreen(
                self.app, self._svc, on_change=lambda: self.app.run_async(self._load())))
            return None
        return key


class ServiceRunlevelsScreen(Screen):
    """Manage which OpenRC runlevels a service starts in (rc-update add/del).

    ``rc-update`` can enable a service into any runlevel — boot, default,
    sysinit, shutdown — but the list screen's quick ``e`` toggle only touches
    ``default``. This screen exposes all of them: Space adds/removes the service
    from the focused runlevel. ``on_change`` (if given) is called after each
    successful toggle so the caller can refresh the runlevels it shows.
    """

    def __init__(self, app: App, service: Service, *, on_change=None) -> None:
        self._svc = service
        self._on_change = on_change
        self._levels = list(reader.RUNLEVELS)
        self._enabled = set(service.runlevels)
        self._walker = urwid.SimpleFocusListWalker([])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, boxed(self._list, title=f"Runlevels · {service.name}"),
            title=f"Runlevels · {service.name}",
            footer_keys=[("Space", "Add/Remove"), ("Esc", "Back")],
            help_text=(
                "Which runlevels this service starts in.\n\n"
                "A ✓ means the service is enabled in that runlevel. Space adds or\n"
                "removes it (rc-update add/del). Most services belong in default;\n"
                "boot is for one-time early setup, shutdown runs on the way down.\n\n"
                "Space  add / remove the focused runlevel\n"
                "Esc    back"
            ),
        )
        self._rebuild()

    def _rebuild(self) -> None:
        prev = self._walker.focus if self._walker else 0
        self._walker[:] = [
            _row(f" [{'✓' if lvl in self._enabled else ' '}] {lvl:<10} "
                 f"{_RUNLEVEL_DESC.get(lvl, '')}")
            for lvl in self._levels
        ]
        self._walker.set_focus(min(prev or 0, len(self._levels) - 1))
        self.app.refresh()

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key in (" ", "enter"):
            self.app.run_async(self._toggle(self._levels[self._walker.focus]))
            return None
        return key

    async def _toggle(self, level: str) -> None:
        enable = level not in self._enabled
        backend = ServicesBackend()
        try:
            await backend.connect()
            ok, _out = await backend.set_enabled(self._svc.name, enable, level)
        except Exception as exc:
            self.app.notify(f"{self._svc.name}: {exc}", error=True)
            await backend.close()
            return
        await backend.close()
        verb = "added to" if enable else "removed from"
        self.app.notify(f"{self._svc.name}: {verb} {level} "
                        f"{'ok' if ok else 'failed'}", error=not ok)
        if not ok:
            return
        self._enabled.add(level) if enable else self._enabled.discard(level)
        # Keep the shared Service in canonical runlevel order so a caller reading
        # svc.runlevels (and our own re-render) stays consistent.
        self._svc.runlevels = [lvl for lvl in reader.RUNLEVELS if lvl in self._enabled]
        self._rebuild()
        if self._on_change is not None:
            self._on_change()
