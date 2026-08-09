"""Streaming apply screen (urwid): preview an emerge plan, then run it live.

Reused by Software Management's Accept (install then depclean), and by the
system update / depclean / sync menu entries. Each ``Plan`` pairs a read-only
preview (run as the user) with a streamed backend operation.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable

import urwid

from gest.core.software import preview
from gest.core.software.backend_client import SoftwareBackend
from gest.tui.runtime import App, Screen, ansi_markup, strip_ansi

# emerge's per-package progress markers, e.g.
#   >>> Emerging (2 of 5) app-editors/vim-9.1::gentoo
#   >>> Installing (2 of 5) app-editors/vim-9.1::gentoo
#   >>> Emerging binary (3 of 5) sys-apps/foo-1.0::gentoo   (--getbinpkg path)
_PROGRESS_RE = re.compile(
    r">>> (Emerging|Installing)(?: binary)? \((\d+) of (\d+)\)\s+(\S+)")


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


def install_binary_plan(atoms: list[str], *, only: bool) -> Plan:
    label = "Install (binary only)" if only else "Install (prefer binary)"
    return Plan(label,
                lambda: preview.preview_install_binary_many(atoms, only=only),
                lambda b, p, f: b.install_binary_multi(atoms, only, p, f))


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
        self._plan_label = ""
        self._walker = urwid.SimpleFocusListWalker(
            [urwid.SelectableIcon(" computing plan …", 0)]
        )
        self._log = urwid.ListBox(self._walker)
        self._phase = urwid.Text(("dim", " Reviewing the plan …"))
        self._bar = urwid.ProgressBar("pb_normal", "pb_complete", 0, 1)
        body = urwid.Pile([
            ("pack", urwid.AttrMap(self._phase, "field")),
            ("pack", self._bar),
            ("pack", urwid.Divider("─")),
            ("weight", 1, self._log),
        ])
        super().__init__(
            app, urwid.LineBox(body, title=verb), title=verb,
            footer_keys=[("F10", verb), ("Esc", "Back")],
        )
        app.run_async(self._preview())

    def _set_phase(self, text: str, attr: str = "field") -> None:
        self._phase.set_text((attr, f" {text}"))

    def _update_progress(self, line: str) -> None:
        """Advance the bar/label from an emerge '(N of M)' marker (ignore else)."""
        m = _PROGRESS_RE.search(strip_ansi(line))
        if not m:
            return
        phase, n, total, atom = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        self._bar.done = max(total, 1)
        # A package is "done" once its Installing phase runs; while Emerging,
        # count the prior ones as complete.
        self._bar.set_completion(n if phase == "Installing" else max(n - 1, 0))
        self._set_phase(f"{self._plan_label}: {phase} {n} of {total} — {atom}")
        self.app.refresh()

    def _append(self, lines: list[str]) -> None:
        for line in lines:
            self._walker.append(urwid.SelectableIcon(ansi_markup(line), 0))
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
        self._set_phase(
            f"Ready — F10 to {self._verb.lower()}" if ok_all
            else "Cannot proceed — see the plan above",
            "ok" if ok_all else "error")
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
            self._update_progress(line)

        def on_finished(code: int) -> None:
            result["code"] = code
            finished.set()

        # Reset the bar for this plan; emerge's own (N of M) drives it (M counts
        # dependencies too, so it reflects the real work, not just marked atoms).
        self._plan_label = plan.label
        self._bar.done, self._bar.current = 1, 0
        self._set_phase(f"{plan.label}: starting …")
        self._append([f"— {plan.label} started —"])
        try:
            started = await plan.run(backend, on_progress, on_finished)
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            denied = "not authorized" in message.lower() or "AccessDenied" in message
            lines = [f"[rejected] {message}"]
            if denied:
                lines.append(
                    "  → an administrator authentication prompt should appear; "
                    "complete it (run gest in your desktop session)."
                )
            self._append(lines)
            await backend.close()
            self.app.notify(
                "authentication declined/cancelled — complete the password prompt"
                if denied else f"failed: {message}",
                error=True,
            )
            return None
        if not started:
            self._append(["[backend declined to start]"])
            await backend.close()
            return None
        await finished.wait()
        await backend.close()
        code = result.get("code", -1)
        if code == 0:
            self._bar.set_completion(self._bar.done)   # fill on success
        self._set_phase(f"{plan.label}: finished (exit {code})",
                        "ok" if code == 0 else "error")
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
