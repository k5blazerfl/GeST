"""Sync Portage Tree (urwid): branded startup, review, then a branded sync run.

Opening reads the syncable repositories behind the branded loading screen
(:class:`SyncLoadingScreen`), then lists them for review (:class:`SyncScreen`).
F10 runs ``emerge --sync`` on a full-screen branded progress screen
(:class:`SyncRunScreen` — GeST logo + per-repo status + bar), updating each row
from emerge's ``>>> Syncing repository 'X'`` / ``Action: sync for repo: X,
returned code = N`` markers (pending → syncing → synced / failed), then a
result. The full raw log is kept on demand (l / View log).
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
from gest.tui.screens.loading import LoadingScreen
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


def _syncable(repos) -> list[_SyncRepo]:
    """The enabled repos that will actually sync (a URI, auto-sync not 'no')."""
    return [_SyncRepo(r.name, r.sync_type, r.sync_uri) for r in repos
            if r.sync_uri and r.auto_sync.strip().lower() != "no"]


class SyncLoadingScreen(LoadingScreen):
    """Branded startup: read the syncable repositories, then hand off to review."""

    def __init__(self, app: App) -> None:
        super().__init__(
            app,
            [{"key": "read", "label": "Read repositories",
              "status": "pending", "detail": ""}],
            title="Sync Portage Tree",
            subtitle="Preparing to sync the Portage tree",
            help_text=("Reading the repositories to sync from "
                       "/etc/portage/repos.conf.\n"
                       "Esc cancels and returns to the main menu."))

    async def _run(self) -> None:
        self._set_step("read", "active")
        self._set_phase("Reading /etc/portage/repos.conf …")
        repos = await self.app.run_blocking(reader.enabled_repos)
        rows = _syncable(repos)
        self._bar.set_completion(1)
        self._set_step("read", "done",
                       f"{len(rows)} repositor{'y' if len(rows) == 1 else 'ies'}")
        self._set_phase("Ready.", "ok")
        if self.app._stack and self.app._stack[-1] is self:   # not cancelled
            self.app.replace(SyncScreen(self.app, preloaded=rows))


class SyncScreen(Screen):
    """Review the repositories that will sync; F10 starts the branded sync run."""

    def __init__(self, app: App, preloaded: list[_SyncRepo] | None = None) -> None:
        self._repos: list[_SyncRepo] = preloaded or []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        self._count = urwid.Text("")

        header = urwid.AttrMap(
            urwid.Text(_fmt("", "Name", "Type", "Sync URI"), wrap="clip"),
            "pane_title")
        table = boxed(
            urwid.Pile([("pack", header), ("pack", urwid.Divider("─")),
                        ("weight", 1, self._list)]),
            title="Repositories")
        self._actions = focusable_actions([
            ("Cancel", app.pop), ("Sync", self._sync)])
        body = NavPile([
            ("weight", 1, table),
            ("pack", self._count),
            ("pack", self._actions),
        ])
        super().__init__(
            app, body, title="Sync Portage Tree",
            footer_keys=[("F10", "Sync"), ("Esc", "Back")],
            help_text=(
                "Sync the Portage ebuild tree — fetch the latest ebuilds/metadata\n"
                "for the repositories below from their sync URIs over the network.\n"
                "It refreshes available versions; it does not change installed\n"
                "packages.\n\n"
                "F10 starts the sync (a full-screen progress screen); a repo that\n"
                "fails doesn't fail the others. Esc goes back."))
        self.configure_pane_cycle(body, [0], action_row=self._actions)
        if preloaded is not None:
            self._render()
        else:
            app.run_async(self._load())

    def _footer_context(self):
        if self._on_action_row():
            return [("Enter", "Activate"), ("Tab", "Next"), ("Esc", "Back")]
        return self._base_footer_keys

    async def _load(self) -> None:
        repos = await self.app.run_blocking(reader.enabled_repos)
        self._repos = _syncable(repos)
        self._render()

    def _render(self) -> None:
        self._walker[:] = [
            row(_fmt(_GLYPH[r.status], r.name, r.sync_type or "—",
                     r.sync_uri or "—"), _ATTR[r.status])
            for r in self._repos] or [urwid.Text(" (no repositories)")]
        n = len(self._repos)
        self._count.set_text(
            ("dim", f" {n} repositor{'y' if n == 1 else 'ies'} to sync"
                    "   ·   F10 Sync") if n
            else ("dim", " No syncable repositories configured."))
        self.app.refresh()

    def _sync(self) -> None:
        if not self._repos:
            self.app.notify("No repositories to sync.", error=True)
            return
        self.app.push(SyncRunScreen(self.app, self._repos))

    def handle_key(self, key):
        if key == "f10":
            self._sync()
            return None
        if key == "esc":
            self.app.pop()
            return None
        return key


class SyncRunScreen(StreamLog, LoadingScreen):
    """Full-screen branded sync: GeST logo + per-repo progress, then a result."""

    def __init__(self, app: App, repos: list[_SyncRepo]) -> None:
        self._repos = [_SyncRepo(r.name, r.sync_type, r.sync_uri) for r in repos]
        self._by_name = {r.name: r for r in self._repos}
        self._total = len(self._repos)
        self._done = False
        self._logfile = None
        self._logpath: str | None = None
        self._refresh_pending = False
        super().__init__(
            app,
            [{"key": "sync", "label": "Sync repositories",
              "status": "active", "detail": ""}],
            title="Sync Portage Tree",
            subtitle="Syncing the Portage tree",
            help_text=(
                "Syncing the Portage tree (emerge --sync).\n"
                "Each repo:  · pending   ▸ syncing   ✓ synced   ✗ failed\n"
                "l views the raw emerge log · Esc returns when finished."))
        self._bar.done = max(self._total, 1)
        self._render()

    def _sub_rows(self, step: dict) -> list:
        return [(_ATTR[r.status], f"        {_GLYPH[r.status]}  {r.name}\n")
                for r in self._repos]

    # -- run ----------------------------------------------------------------

    async def _run(self) -> None:
        self._set_phase("Syncing repositories …")
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
        self._done = True
        if code is not None:                   # settle any repo still in flight
            for r in self._repos:
                if r.status == "syncing":
                    r.status = "synced" if code == 0 else "failed"
                elif r.status == "pending" and code == 0:
                    r.status = "synced"
        self._bar.set_completion(self._total)
        synced = [r.name for r in self._repos if r.status == "synced"]
        failed = [r.name for r in self._repos if r.status == "failed"]
        if code is None:
            self._set_step("sync", "failed")
            reason = error or ("administrator authentication was declined, or the "
                               "backend was unavailable")
            title, ok, msg = "Not started", False, (
                f"The sync did not start — {reason}. Nothing was changed.")
        elif not failed:
            self._set_step("sync", "done", f"{len(synced)} synced")
            title, ok, msg = "Completed", True, (
                f"All {len(synced)} repositories synced.")
        elif synced:
            self._set_step("sync", "failed",
                           f"{len(synced)} of {len(synced) + len(failed)}")
            title, ok, msg = "Partially synced", False, (
                f"{len(synced)} of {len(synced) + len(failed)} synced; "
                f"failed: {', '.join(failed)}. The rest were updated.")
        else:
            self._set_step("sync", "failed")
            title, ok, msg = "Failed", False, (
                f"All {len(failed)} repositories failed to sync: "
                f"{', '.join(failed)}.")
        self._set_phase(f"Sync: {title.lower()}", "ok" if ok else "error")
        self._result_modal(title, ok, msg)

    def _result_modal(self, title: str, ok: bool, message: str) -> None:
        self.app.notify(title.lower(), error=not ok)
        if self._logpath:
            message = f"{message}\n\nFull log: {self._logpath}"

        def back():
            self.app.pop()   # the result modal
            self.app.pop()   # the run screen → back to the review

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
        if key in ("l", "L"):
            self._view_log()
            return None
        if key == "esc":
            if self._done:
                self.app.pop()       # back to the review
            return None              # ignore Esc mid-sync
        return key
