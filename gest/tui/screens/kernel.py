"""Kernel build (urwid): show source state, configure a build, stream it.

Info is read unprivileged. Building picks its path by runtime
(``core.exec.choose_executor``): in-process via `build()` when running as root
(live CD), else the streaming polkit-gated `KernelBackend` on an installed
system. Either way the output streams into the log; the direct path also drives a
per-step phase label.
"""

from __future__ import annotations

import asyncio
import contextlib

import urwid

from gest.core.exec.executor import DirectExecutor
from gest.core.exec.select import choose_executor
from gest.core.exec.steps import StepError
from gest.core.kernel import build, reader
from gest.core.kernel.backend_client import KernelBackend
from gest.tui.runtime import App, Modal, Screen, boxed, strip_ansi


class KernelScreen(Screen):
    def __init__(self, app: App) -> None:
        self._info_data: reader.KernelBuildInfo | None = None
        self._info = urwid.Text(" loading …")
        self._phase = urwid.Text(("dim", " Press b to build a kernel."))
        self._log_walker = urwid.SimpleFocusListWalker([])
        self._log = urwid.ListBox(self._log_walker)
        pile = urwid.Pile([
            ("pack", self._info),
            ("pack", urwid.Divider()),
            ("pack", urwid.AttrMap(self._phase, "field")),
            ("pack", urwid.Divider("─")),
            ("weight", 1, boxed(self._log, title="Output")),
        ])
        super().__init__(
            app, pile, title="Kernel Build",
            footer_keys=[("b", "Build"), ("Esc", "Back")],
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        info = await self.app.run_blocking(reader.build_info)
        self._info_data = info
        tools = ", ".join(
            [t for t, ok in (("genkernel", info.genkernel), ("dracut", info.dracut)) if ok]
        ) or "none"
        self._info.set_text("\n".join([
            f" Kernel source : {info.current or '—'}",
            f" .config       : {'present' if info.has_config else 'missing'}",
            f" Sources        : {', '.join(info.sources) or '—'}",
            f" Build tools   : {tools}",
            f" CPUs (-j)     : {info.cpus}",
        ]))
        self.app.refresh()

    def _log_lines(self, lines: list[str]) -> None:
        for ln in lines:
            self._log_walker.append(urwid.Text(strip_ansi(ln)))
        del self._log_walker[:-1000]
        with contextlib.suppress(Exception):
            self._log_walker.set_focus(len(self._log_walker) - 1)
        self.app.refresh()

    def _set_phase(self, text: str, attr: str = "field") -> None:
        self._phase.set_text((attr, f" {text}"))
        self.app.refresh()

    # -- configure ----------------------------------------------------------

    def _configure(self) -> None:
        info = self._info_data
        cpus = info.cpus if info else 1
        method_group: list = []
        gk_rb = urwid.RadioButton(method_group, "genkernel  (automated: config + build + install)")
        urwid.RadioButton(method_group, "make  (manual: needs an existing .config)")
        jobs = urwid.Edit("Parallel jobs (-j) : ", str(cpus))
        kconfig = urwid.Edit("genkernel config   : ", "")
        initramfs = urwid.CheckBox("make: build an initramfs with dracut", state=True)

        def start():
            method = "genkernel" if gk_rb.state else "make"
            try:
                job_count = int(jobs.edit_text.strip() or cpus)
            except ValueError:
                self.app.notify("Jobs must be a number.", error=True)
                return
            source_dir = info.source_dir if info and info.source_dir else "/usr/src/linux"
            config = build.BuildConfig(
                method=method, source_dir=source_dir, jobs=job_count,
                kernel_config=kconfig.edit_text.strip(), initramfs=initramfs.state)
            try:
                build.build_steps(config)          # validate before we commit
            except ValueError as exc:
                self.app.notify(str(exc), error=True)
                return
            self.app.pop()
            self.app.run_async(self._build(config))

        modal = Modal(
            self.app, "Build a kernel",
            [urwid.Text(("hint", "genkernel builds and installs a kernel for you; "
                                 "make uses the source tree's existing .config.")),
             urwid.Divider(), gk_rb, method_group[1],
             urwid.Divider(), jobs, kconfig, initramfs],
            [("Build", start), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 76), height=("relative", 64))

    # -- run ----------------------------------------------------------------

    async def _build(self, config: build.BuildConfig) -> None:
        self._log_walker[:] = []
        self._set_phase(f"Building kernel ({config.method}) …")
        executor = choose_executor()
        if isinstance(executor, DirectExecutor):
            await self._build_direct(config, executor)
        else:
            await self._build_backend(config)

    async def _build_direct(self, config, executor) -> None:
        labels = [s.label for s in build.build_steps(config)]

        def on_step(index: int) -> None:
            if 0 <= index < len(labels):
                self._set_phase(labels[index])

        try:
            await build.build(config, executor, on_progress=self._log_lines, on_step=on_step)
        except StepError as exc:
            self._log_lines(exc.result.output.splitlines())
            self._finish(False, f"{exc.step.label} failed")
        except Exception as exc:
            self._finish(False, str(exc))
        else:
            self._finish(True)

    async def _build_backend(self, config) -> None:
        finished = asyncio.Event()
        result: dict[str, int | None] = {"code": None}

        def on_finished(code: int) -> None:
            result["code"] = code
            finished.set()

        backend = KernelBackend()
        try:
            await backend.connect()
            started = await backend.build(
                config, on_progress=self._log_lines, on_finished=on_finished)
        except Exception as exc:
            with contextlib.suppress(Exception):
                await backend.close()
            self._finish(False, str(exc))
            return
        if not started:
            await backend.close()
            self._finish(False, "the build did not start (authentication declined?)")
            return
        await finished.wait()
        await backend.close()
        self._finish(result["code"] == 0)

    def _finish(self, ok: bool, message: str = "") -> None:
        self._set_phase("done" if ok else (message or "failed"), "ok" if ok else "error")
        self.app.notify("kernel built" if ok else "kernel build failed", error=not ok)

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key in ("b", "B"):
            if self._info_data is None:
                self.app.notify("Still loading …", error=True)
            else:
                self._configure()
            return None
        return key
