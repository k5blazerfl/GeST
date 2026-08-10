"""Streaming apply screen (urwid): preview an emerge plan, then run it live.

Reused by Software Management's Accept (install then depclean), and by the
system update / depclean / sync menu entries. Each ``Plan`` pairs a read-only
preview (run as the user) with a streamed backend operation.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import tempfile
from collections.abc import Awaitable, Callable

import urwid

from gest.core.software import preview
from gest.core.software.backend_client import SoftwareBackend
from gest.tui.runtime import App, Modal, Screen, ansi_markup, strip_ansi

# emerge's per-package progress markers, e.g.
#   >>> Emerging (2 of 5) app-editors/vim-9.1::gentoo
#   >>> Installing (2 of 5) app-editors/vim-9.1::gentoo
#   >>> Emerging binary (3 of 5) sys-apps/foo-1.0::gentoo   (--getbinpkg path)
_PROGRESS_RE = re.compile(
    r">>> (Emerging|Installing)(?: binary)? \((\d+) of (\d+)\)\s+(\S+)")

# emerge --sync prints one summary line per repository at the end, e.g.
#   Action: sync for repo: gentoo, returned code = 0
# Captured so a sync where only a flaky overlay failed reads as "Partially
# synced" (naming the culprit) rather than a flat "Failed".
_SYNC_RESULT_RE = re.compile(
    r"sync for repo:\s+([\w][\w.+-]*),\s+returned code\s*=\s*(\d+)")

# Cap the on-screen scrollback. A failing build streams its whole compiler/error
# log — often tens of thousands of lines — one D-Bus signal per line; retaining a
# urwid widget for every one grows memory unboundedly and makes each redraw
# slower until the UI locks up. Keep the last _MAX_LOG_LINES (the error tail is
# what matters on failure) and spill the complete log to a file.
_MAX_LOG_LINES = 2000


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


class StreamLog:
    """Mixin: a lazily-created full on-disk log spill + coalesced redraws.

    The host screen must initialise ``self._logfile = None``,
    ``self._logpath = None`` and ``self._refresh_pending = False`` in its
    ``__init__`` and expose ``self.app``. Shared by ApplyScreen and the Clean Up
    removal-progress screen so streamed output is preserved on disk even when the
    visible view is capped (ApplyScreen) or organized (Clean Up).
    """

    def _schedule_refresh(self) -> None:
        """Collapse a burst of streamed lines into one redraw on the next tick."""
        if self._refresh_pending:
            return
        self._refresh_pending = True
        self.app.loop.call_soon(self._flush_refresh)

    def _flush_refresh(self) -> None:
        self._refresh_pending = False
        self.app.refresh()

    def _write_log(self, lines: list[str]) -> None:
        """Append plain-text lines to the full on-disk log (created lazily).

        The on-screen view may be capped or organized, so this file is the
        complete record a failed removal/build can be debugged from.
        """
        if self._logfile is None:
            fd, self._logpath = tempfile.mkstemp(prefix="gest-apply-", suffix=".log")
            self._logfile = os.fdopen(fd, "w", buffering=1)
        for line in lines:
            with contextlib.suppress(Exception):
                self._logfile.write(strip_ansi(line) + "\n")

    def _close_log(self) -> None:
        if self._logfile is not None:
            with contextlib.suppress(Exception):
                self._logfile.close()
            self._logfile = None


class ApplyScreen(StreamLog, Screen):
    def __init__(self, app: App, plans: list[Plan], *, verb: str = "Apply",
                 on_done=None) -> None:
        self._plans = plans
        self._verb = verb
        self._on_done = on_done
        self._ready = False
        self._running = False
        self._done = False
        self._plan_label = ""
        self._logfile = None       # full on-disk log, created on first line
        self._logpath: str | None = None
        self._refresh_pending = False
        self._sync_results: dict[str, int] = {}  # repo -> emerge --sync exit code
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
        self._schedule_refresh()

    def _note_sync_result(self, line: str) -> None:
        """Record a per-repo `emerge --sync` result line, if this is one."""
        m = _SYNC_RESULT_RE.search(strip_ansi(line))
        if m:
            self._sync_results[m.group(1)] = int(m.group(2))

    def _sync_outcome(self, overall: int) -> tuple[str, bool, str] | None:
        """For a run that captured per-repo sync results, return
        (title, ok, message); else None so the caller uses generic wording.

        A sync where some repos succeeded and others failed is reported as a
        partial success naming each repo, rather than a flat failure — one flaky
        third-party overlay shouldn't read as "the sync failed".
        """
        if not self._sync_results:
            return None
        ok = sorted(r for r, c in self._sync_results.items() if c == 0)
        fail = sorted(r for r, c in self._sync_results.items() if c != 0)
        body = "\n".join(
            [f"  ✓ {r}" for r in ok]
            + [f"  ✗ {r} (code {self._sync_results[r]})" for r in fail]
        )
        if not fail:
            return ("Completed", True, f"All {len(ok)} repositories synced:\n{body}")
        if ok:
            return ("Partially synced", False,
                    f"{len(ok)} of {len(ok) + len(fail)} repositories synced; "
                    f"{len(fail)} failed:\n{body}\n\n"
                    "The repositories that succeeded were updated.")
        return ("Failed", False,
                f"All {len(fail)} repositories failed to sync:\n{body}")

    def _append(self, lines: list[str]) -> None:
        self._write_log(lines)
        for line in lines:
            self._walker.append(urwid.SelectableIcon(ansi_markup(line), 0))
        # Bound the scrollback so a failing build's error dump can't grow memory
        # (and per-redraw cost) without limit; the full log is on disk.
        overflow = len(self._walker) - _MAX_LOG_LINES
        if overflow > 0:
            del self._walker[:overflow]
        self._walker.set_focus(len(self._walker) - 1)
        self._schedule_refresh()

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

        def on_progress(lines: list[str]) -> None:
            # The backend batches output, so ``lines`` is a group of emerge
            # output lines, not a single one.
            self._append([ln.rstrip("\n") for ln in lines])
            for ln in lines:
                self._update_progress(ln)
                self._note_sync_result(ln)

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
        aborted = False
        for plan in self._plans:
            code = await self._run_one(plan)
            if code is None:      # a plan failed to start / authorize
                aborted = True
                break
            overall = overall or code
        self._running = False
        self._done = True
        self._close_log()
        if not aborted and self._on_done is not None:
            # never let a refresh hiccup swallow the result prompt
            with contextlib.suppress(Exception):
                self._on_done()   # refresh the caller's installed list
        sync_outcome = self._sync_outcome(overall)
        if aborted:
            self._finish("Not started", False,
                         "The operation did not start — administrator authentication "
                         "was declined, or the backend was unavailable. Nothing was "
                         "changed.")
        elif sync_outcome is not None:
            # A sync run: report per-repo so a single failed overlay doesn't read
            # as a total failure (and a full success names what was updated).
            self._finish(*sync_outcome)
        elif overall == 0:
            self._finish("Completed", True,
                         f"All package operations completed successfully "
                         f"(emerge exit {overall}).")
        else:
            self._finish("Failed", False,
                         f"A problem occurred — emerge exited {overall}. The changes "
                         "may be incomplete; review the log above for details.")

    def _finish(self, title: str, ok: bool, message: str) -> None:
        """Show an unmistakable success/failure prompt when the run ends."""
        self.app.notify(title.lower(), error=not ok)
        self._set_phase(f"{self._verb}: {title.lower()}", "ok" if ok else "error")
        if self._logpath:
            message = f"{message}\n\nFull log: {self._logpath}"

        def back():
            self.app.pop()   # the result modal
            self.app.pop()   # the apply screen → back to the caller

        modal = Modal(self.app, title,
                      [urwid.Text(("ok" if ok else "error", message))],
                      [("Back", back), ("View log", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 62), height=("relative", 40))

    def handle_key(self, key):
        if key == "esc" and not self._running:
            self.app.pop()
            return None
        if key == "f10" and self._ready and not self._running and not self._done:
            self.app.run_async(self._apply())
            return None
        return key
