"""Sync Portage Tree (urwid): a compact per-repository sync instead of a raw dump.

``emerge --sync`` streams verbose rsync/git output; this lists the repositories
that will sync (from repos.conf) and updates each row's status live from emerge's
``>>> Syncing repository 'X'`` / ``Action: sync for repo: X, returned code = N``
markers (pending → syncing → synced / failed), with a progress bar and a per-repo
result. The full raw log is kept on demand (l / View log). Since ``emerge --sync``
has no ``--pretend``, the review list and the progress list are the same rows, so
this is one screen: review, then F10 syncs in place.
"""

from __future__ import annotations

import asyncio
import contextlib

import urwid

from gest.core.repos import reader
from gest.core.software import sync
from gest.core.software.backend_client import SoftwareBackend
from gest.tui.runtime import App, Modal, NavPile, Screen, boxed, focusable_actions
from gest.tui.screens.apply import RawLogScreen, StreamLog
from gest.tui.screens.runscreen import clip, row

_STATUS_W = 2
_NAME_W = 24
_TYPE_W = 9

_GLYPH = {"pending": "·", "syncing": "▸", "synced": "✓", "failed": "✗"}
_ATTR = {"pending": "dim", "syncing": None, "synced": "dim", "failed": "error"}


def _fmt(glyph: str, name: str, stype: str, uri: str) -> str:
    return (f"{glyph:<{_STATUS_W}}{clip(name, _NAME_W):<{_NAME_W}}"
            f"{clip(stype, _TYPE_W):<{_TYPE_W}}{uri}")


class _SyncRepo:
    __slots__ = ("name", "status", "sync_type", "sync_uri")

    def __init__(self, name, sync_type="", sync_uri=""):
        self.name, self.sync_type, self.sync_uri = name, sync_type, sync_uri
        self.status = "pending"


class SyncScreen(StreamLog, Screen):
    def __init__(self, app: App) -> None:
        self._repos: list[_SyncRepo] = []
        self._by_name: dict[str, _SyncRepo] = {}
        self._total = 0
        self._running = False
        self._done = False
        self._logfile = None
        self._logpath: str | None = None
        self._refresh_pending = False

        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        self._phase = urwid.Text(("dim", " Reading repositories …"))
        self._bar = urwid.ProgressBar("pb_normal", "pb_complete", 0, 1)

        header = urwid.AttrMap(
            urwid.Text(_fmt("", "Name", "Type", "Sync URI"), wrap="clip"), "pane_title")
        table = boxed(
            urwid.Pile([("pack", header), ("pack", urwid.Divider("─")),
                        ("weight", 1, self._list)]),
            title="Repositories")
        self._actions = focusable_actions([
            ("Cancel", lambda: self._running or self.app.pop()),
            ("Sync", self._start)])
        body = NavPile([
            ("pack", urwid.AttrMap(self._phase, "field")),
            ("pack", self._bar),
            ("pack", urwid.Divider("─")),
            ("weight", 1, table),
            ("pack", self._actions),
        ])
        super().__init__(
            app, body, title="Sync Portage Tree",
            footer_keys=[("F10", "Sync"), ("l", "View log"), ("Esc", "Back")],
            help_text=(
                "Sync the Portage ebuild tree — fetch the latest ebuilds/metadata\n"
                "for the repositories below from their sync URIs over the network.\n"
                "It refreshes available versions; it does not change installed\n"
                "packages.\n\n"
                "Each row shows its status:  · pending   ▸ syncing   ✓ synced"
                "   ✗ failed\n"
                "F10 starts the sync; a repo that fails doesn't fail the others "
                "(the result names each). l views the raw emerge log; Esc goes back."
            ),
        )
        self.configure_pane_cycle(body, [3], action_row=self._actions)
        app.run_async(self._load())

    def _footer_context(self):
        if self._on_action_row():
            return [("Enter", "Activate"), ("l", "View log"),
                    ("Tab", "Next"), ("Esc", "Back")]
        return self._base_footer_keys

    async def _load(self) -> None:
        repos = await self.app.run_blocking(reader.enabled_repos)
        self._repos = [_SyncRepo(r.name, r.sync_type, r.sync_uri) for r in repos
                       if r.sync_uri and r.auto_sync.strip().lower() != "no"]
        self._by_name = {sr.name: sr for sr in self._repos}
        self._total = len(self._repos)
        self._bar.done = max(self._total, 1)
        self._render()
        n = self._total
        self._set_phase(f"Ready — F10 to sync {n} repositor{'y' if n == 1 else 'ies'}."
                        if n else "No syncable repositories configured.", "dim")

    def _render(self) -> None:
        rows = [row(_fmt(_GLYPH[r.status], r.name, r.sync_type or "—",
                         r.sync_uri or "—"), _ATTR[r.status])
                for r in self._repos] or [urwid.Text(" (no repositories)")]
        self._walker[:] = rows
        self._schedule_refresh()

    def _set_phase(self, text: str, attr: str = "field") -> None:
        self._phase.set_text((attr, f" {text}"))

    # -- run ----------------------------------------------------------------

    def _start(self) -> None:
        if self._running or self._done or not self._repos:
            return
        self._running = True
        self.app.run_async(self._run())

    async def _run(self) -> None:
        finished = asyncio.Event()
        code: dict[str, int | None] = {"v": None}

        def on_progress(lines: list[str]) -> None:
            self._write_log(lines)
            for ln in lines:
                self._consume(ln)

        def on_finished(exit_code: int) -> None:
            code["v"] = exit_code
            finished.set()

        backend = SoftwareBackend()
        try:
            await backend.connect()
            started = await backend.sync(on_progress, on_finished)
        except Exception as exc:
            with contextlib.suppress(Exception):
                await backend.close()
            self._finish(None, str(exc))
            return
        if not started:
            await backend.close()
            self._finish(None, "the sync did not start")
            return
        self._set_phase("Syncing repositories …")
        await finished.wait()
        await backend.close()
        self._close_log()
        self._finish(code["v"], "")

    def _consume(self, line: str) -> None:
        ev = sync.parse_sync_event(line)
        if ev is None:
            return
        repo = self._by_name.get(ev.repo)
        if repo is None:                       # a repo not in repos.conf's list
            repo = _SyncRepo(ev.repo)
            self._repos.append(repo)
            self._by_name[ev.repo] = repo
            self._total = len(self._repos)
            self._bar.done = max(self._total, 1)
        if ev.kind == "start":
            repo.status = "syncing"
            self._set_phase(f"Syncing {ev.repo} …")
        else:                                  # result
            repo.status = "synced" if ev.code == 0 else "failed"
            done = sum(1 for r in self._repos if r.status in ("synced", "failed"))
            self._bar.set_completion(min(done, self._total))
        self._render()

    def _finish(self, code: int | None, error: str) -> None:
        self._running = False
        self._done = True
        if code is not None:                   # settle any repo still in flight
            for r in self._repos:
                if r.status == "syncing":
                    r.status = "synced" if code == 0 else "failed"
                elif r.status == "pending" and code == 0:
                    r.status = "synced"
        self._bar.set_completion(self._total)
        self._render()
        synced = [r.name for r in self._repos if r.status == "synced"]
        failed = [r.name for r in self._repos if r.status == "failed"]
        if code is None:
            reason = error or ("administrator authentication was declined, or the "
                               "backend was unavailable")
            title, ok, msg = "Not started", False, (
                f"The sync did not start — {reason}. Nothing was changed.")
        elif not failed:
            title, ok, msg = "Completed", True, (
                f"All {len(synced)} repositories synced.")
        elif synced:
            title, ok, msg = "Partially synced", False, (
                f"{len(synced)} of {len(synced) + len(failed)} synced; "
                f"failed: {', '.join(failed)}. The rest were updated.")
        else:
            title, ok, msg = "Failed", False, (
                f"All {len(failed)} repositories failed to sync: {', '.join(failed)}.")
        self._set_phase(f"Sync: {title.lower()}", "ok" if ok else "error")
        self._result_modal(title, ok, msg)

    def _result_modal(self, title: str, ok: bool, message: str) -> None:
        self.app.notify(title.lower(), error=not ok)
        if self._logpath:
            message = f"{message}\n\nFull log: {self._logpath}"

        def back():
            self.app.pop()   # the result modal
            self.app.pop()   # the sync screen

        def view():
            self.app.pop()
            self._view_log()

        def to_menu():
            self.app.pop()   # the result modal
            self.app.pop_to_root()   # back to the Control Center menu

        modal = Modal(self.app, title,
                      [urwid.Text(("ok" if ok else "error", message))],
                      [("Back", back), ("View log", view),
                       ("Main menu", to_menu)])
        self.app.push_modal(modal, width=("relative", 62), height=("relative", 40))

    def _view_log(self) -> None:
        self.app.push(RawLogScreen(self.app, self._logpath))

    def handle_key(self, key):
        if key == "f10":
            self._start()
        elif key in ("l", "L"):
            self._view_log()
        elif key == "esc" and not self._running:
            self.app.pop()
        else:
            return key
        return None
