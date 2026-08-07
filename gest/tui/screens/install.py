"""Install screen: show an `emerge --pretend` preview, then merge on confirm.

Flow:
  1. On open, run the preview (read-only, as the user) and display the plan.
  2. If the plan resolves, enable **Install**.
  3. On Install, connect to the privileged backend and stream the merge output
     live. If the backend isn't installed/running, say so clearly rather than
     failing opaquely.
"""

from __future__ import annotations

import asyncio

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, RichLog, Static

from gest.core.software import preview
from gest.core.software.backend_client import SoftwareBackend


class InstallScreen(Screen):
    """Preview-and-install a single package atom."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("i", "install", "Install"),
        Binding("q", "app.quit", "Quit"),
    ]

    _VERBS = {
        "install": "Install",
        "rebuild": "Rebuild",
        "world": "System update",
        "depclean": "Remove",
        "sync": "Sync",
    }

    def __init__(self, atom: str, mode: str = "install") -> None:
        super().__init__()
        self.atom = atom
        self.mode = mode
        self._verb = self._VERBS[mode]
        self._display = atom or "orphaned packages"
        self._installing = False
        self._done = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"{self._verb} preview — {self._display}", id="install-title")
        yield Static(" computing emerge plan …", id="install-status")
        yield RichLog(id="log", highlight=False, markup=False, wrap=False)
        with Horizontal(id="install-buttons"):
            yield Button(self._verb, id="install", variant="success", disabled=True)
            yield Button("Cancel", id="cancel", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Software Management"
        self.run_preview()

    # -- helpers ------------------------------------------------------------

    def _status(self, text: str) -> None:
        self.query_one("#install-status", Static).update(text)

    def _log(self) -> RichLog:
        return self.query_one("#log", RichLog)

    # -- preview (read-only, threaded) --------------------------------------

    @work(thread=True, exclusive=True)
    def run_preview(self) -> None:
        if self.mode == "world":
            result = preview.preview_world()
        elif self.mode == "sync":
            result = preview.preview_sync()
        elif self.mode == "depclean":
            result = preview.preview_depclean(self.atom)
        else:
            result = preview.preview_install(
                self.atom, changed_use=self.mode == "rebuild"
            )
        self.app.call_from_thread(self._show_preview, result)

    def _show_preview(self, result: preview.PreviewResult) -> None:
        log = self._log()
        for line in result.output.splitlines():
            log.write(line)
        if result.ok:
            self._status(result.summary)
            install = self.query_one("#install", Button)
            install.disabled = False
            install.focus()  # Enter now confirms the merge — no mouse needed
        else:
            self._status(f"cannot proceed: {result.summary}")

    # -- actions ------------------------------------------------------------

    def action_back(self) -> None:
        if not self._installing:
            self.app.pop_screen()

    def action_install(self) -> None:
        if self._installing or self._done:
            return
        btn = self.query_one("#install", Button)
        if btn.disabled:
            return
        self._installing = True
        btn.disabled = True
        self.query_one("#cancel", Button).focus()
        self._status(f"{self._verb.lower()}ing {self.atom} …")
        self.run_install()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.action_back()
        elif event.button.id == "install":
            self.action_install()

    # -- install (privileged, streamed via the backend) ---------------------

    @work(exclusive=True)
    async def run_install(self) -> None:
        log = self._log()
        backend = SoftwareBackend()
        try:
            await backend.connect()
        except Exception as exc:  # noqa: BLE001 - report any connection failure
            log.write(f"[backend unavailable] {exc}")
            log.write("The privileged backend isn't installed or running.")
            log.write("See gest/backend/README.md to install the root service.")
            self._status("backend unavailable — cannot perform the merge")
            self._reset_after_failure()
            return

        finished = asyncio.Event()
        result: dict[str, int] = {}

        def on_progress(line: str) -> None:
            log.write(line.rstrip("\n"))

        def on_finished(code: int) -> None:
            result["code"] = code
            finished.set()

        try:
            if self.mode == "world":
                started = await backend.update_world(on_progress, on_finished)
            elif self.mode == "sync":
                started = await backend.sync(on_progress, on_finished)
            elif self.mode == "depclean":
                started = await backend.depclean(self.atom, on_progress, on_finished)
            elif self.mode == "rebuild":
                started = await backend.rebuild(self.atom, on_progress, on_finished)
            else:
                started = await backend.install(self.atom, on_progress, on_finished)
        except Exception as exc:  # noqa: BLE001 - polkit denial etc.
            log.write(f"[merge rejected] {exc}")
            self._status("not authorized — merge rejected")
            await backend.close()
            self._reset_after_failure()
            return

        if not started:
            log.write("[backend declined to start the merge]")
            self._status("merge not started")
            await backend.close()
            self._reset_after_failure()
            return

        log.write(f"— {self._verb.lower()} started for {self._display} —")
        await finished.wait()
        await backend.close()
        code = result.get("code", -1)
        self._installing = False
        self._done = True
        self._status(f"{'completed' if code == 0 else 'failed'} (exit code {code})")
        self.query_one("#cancel", Button).label = "Back"

    def _reset_after_failure(self) -> None:
        self._installing = False
        self.query_one("#cancel", Button).label = "Back"
