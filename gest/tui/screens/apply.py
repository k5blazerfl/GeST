"""Streaming apply screen (urwid): preview an emerge plan, then run it live.

Reused by Software Management's Accept (install then depclean), and by the
system update / depclean / sync menu entries. Each ``Plan`` pairs a read-only
preview (run as the user) with a streamed backend operation.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import urwid

from gest.core.software import preview
from gest.core.software.backend_client import SoftwareBackend
from gest.tui.runtime import App, Screen


class Plan:
    """One preview+run step. ``preview`` is a blocking callable returning a
    PreviewResult; ``run`` starts the streamed op and returns whether it began.
    """

    def __init__(self, label: str, preview_fn: Callable, run_fn: Callable):
        self.label = label
        self.preview = preview_fn
        self.run: Callable[..., Awaitable[bool]] = run_fn


def world_plan() -> Plan:
    return Plan("System update", preview.preview_world,
                lambda b, p, f: b.update_world(p, f))


def sync_plan() -> Plan:
    return Plan("Sync", preview.preview_sync, lambda b, p, f: b.sync(p, f))


def depclean_plan(atom: str = "") -> Plan:
    return Plan("Remove", lambda: preview.preview_depclean(atom),
                lambda b, p, f: b.depclean(atom, p, f))


def rebuild_plan(atom: str) -> Plan:
    return Plan("Rebuild", lambda: preview.preview_install(atom, changed_use=True),
                lambda b, p, f: b.rebuild(atom, p, f))


def install_plan(atoms: list[str]) -> Plan:
    return Plan("Install", lambda: preview.preview_install_many(atoms),
                lambda b, p, f: b.install_multi(atoms, p, f))


def remove_plan(atoms: list[str]) -> Plan:
    return Plan("Remove", lambda: preview.preview_depclean_many(atoms),
                lambda b, p, f: b.depclean_multi(atoms, p, f))


class ApplyScreen(Screen):
    def __init__(self, app: App, plans: list[Plan], *, verb: str = "Apply",
                 on_done=None) -> None:
        self._plans = plans
        self._verb = verb
        self._on_done = on_done
        self._ready = False
        self._running = False
        self._done = False
        self._walker = urwid.SimpleFocusListWalker(
            [urwid.SelectableIcon(" computing plan …", 0)]
        )
        self._log = urwid.ListBox(self._walker)
        super().__init__(
            app, urwid.LineBox(self._log, title=verb), title=verb,
            footer_keys=[("F10", verb), ("Esc", "Back")],
        )
        app.run_async(self._preview())

    def _append(self, lines: list[str]) -> None:
        for line in lines:
            self._walker.append(urwid.SelectableIcon(line, 0))
        self._walker.set_focus(len(self._walker) - 1)
        self.app.refresh()

    async def _preview(self) -> None:
        self._walker[:] = []
        ok_all = True
        for plan in self._plans:
            result = await self.app.run_blocking(plan.preview)
            self._append([f"— {plan.label} —", *result.output.splitlines(), ""])
            if not result.ok:
                ok_all = False
        self._ready = ok_all
        self.app.notify(
            f"Ready — F10 to {self._verb.lower()}" if ok_all else "Cannot proceed",
            error=not ok_all,
        )

    async def _run_one(self, plan: Plan) -> int | None:
        """Run one plan, streaming its output; return its exit code (None on
        a failure to start/authorize)."""
        backend = SoftwareBackend()
        try:
            await backend.connect()
        except Exception as exc:
            self._append([f"[backend unavailable] {exc}"])
            self.app.notify("backend unavailable", error=True)
            return None
        finished = asyncio.Event()
        result: dict[str, int] = {}

        def on_progress(line: str) -> None:
            self._append([line.rstrip("\n")])

        def on_finished(code: int) -> None:
            result["code"] = code
            finished.set()

        self._append([f"— {plan.label} started —"])
        try:
            started = await plan.run(backend, on_progress, on_finished)
        except Exception as exc:
            self._append([f"[rejected] {exc}"])
            await backend.close()
            self.app.notify("not authorized — rejected", error=True)
            return None
        if not started:
            self._append(["[backend declined to start]"])
            await backend.close()
            return None
        await finished.wait()
        await backend.close()
        code = result.get("code", -1)
        self._append([f"— {plan.label} finished (exit {code}) —", ""])
        return code

    async def _apply(self) -> None:
        self._running = True
        overall = 0
        for plan in self._plans:
            code = await self._run_one(plan)
            if code is None:
                self._running = False
                return
            overall = overall or code
        self._running = False
        self._done = True
        self.app.notify(
            f"completed (exit {overall})" if overall == 0 else f"failed (exit {overall})",
            error=overall != 0,
        )
        if self._on_done is not None:
            self._on_done()

    def handle_key(self, key):
        if key == "esc" and not self._running:
            self.app.pop()
            return None
        if key == "f10" and self._ready and not self._running and not self._done:
            self.app.run_async(self._apply())
            return None
        return key
