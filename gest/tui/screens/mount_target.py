"""Assemble an install target (urwid): mount freshly-made filesystems under a
target root, then generate and write that system's /etc/fstab.

The continuation of the partitioner — reached from its completion modal. All the
dangerous logic (mount ordering, target-root safety, fstab generation) lives in
``core/disk/mount``; this screen only builds a target root, reviews the derived
plan, and drives the apply. Applying picks its path by runtime
(``core.exec.choose_executor``): in-process as root on a live CD, or the
polkit-gated backend on an installed system.
"""

from __future__ import annotations

import contextlib

import urwid

from gest.core.disk import mount, reader
from gest.core.disk.backend_client import DiskBackend
from gest.core.disk.model import BlockDevice, DiskPlan
from gest.core.disk.mount import MountPlan
from gest.core.exec.executor import DirectExecutor
from gest.core.exec.select import choose_executor
from gest.core.exec.steps import StepError
from gest.tui.runtime import App, Modal, NavPile, Screen, boxed, strip_ansi

DEFAULT_TARGET_ROOT = "/mnt/gentoo"


class MountTargetScreen(Screen):
    """Choose a target root, review the derived mount plan, launch the apply."""

    def __init__(self, app: App, disk_plan: DiskPlan, devices: list[BlockDevice],
                 mounts: str) -> None:
        self._disk_plan = disk_plan
        self._devices = devices
        self._mounts = mounts
        self._root = DEFAULT_TARGET_ROOT
        self._plan: MountPlan | None = None
        self._root_text = urwid.Text("")
        self._plan_walker = urwid.SimpleFocusListWalker([urwid.Text(" ")])
        self._plan_list = urwid.ListBox(self._plan_walker)
        self._pile = NavPile([
            ("pack", urwid.AttrMap(self._root_text, "field")),
            ("pack", urwid.Divider("─")),
            boxed(self._plan_list, title="Mount Plan  (root-first, then swap)"),
        ])
        super().__init__(
            app, self._pile, title="Mount Install Target",
            footer_keys=[("t", "Target root"), ("F10", "Mount"), ("Esc", "Back")],
        )
        self._rederive()

    def _rederive(self) -> None:
        try:
            self._plan = mount.derive_mount_plan(self._disk_plan, self._root)
        except ValueError as exc:
            self._plan = None
            self.app.notify(str(exc), error=True)
        self._render()

    def _render(self) -> None:
        self._root_text.set_text(f" Target root: {self._root}")
        rows: list[urwid.Widget] = []
        if self._plan is None:
            rows.append(urwid.Text(" (invalid target root)"))
        else:
            rows.append(urwid.Text(("pane_title", "  Filesystems")))
            for m in self._plan.mounts:
                dest = mount.target_abs(self._plan.root, m.path)
                rows.append(urwid.Text(f"    {m.device:<14} {m.fstype:<6} → {dest}"))
            if self._plan.swap:
                rows.append(urwid.Divider("─"))
                rows.append(urwid.Text(("pane_title", "  Swap")))
                for dev in self._plan.swap:
                    rows.append(urwid.Text(("dim", f"    swapon {dev}")))
        self._plan_walker[:] = rows
        self.app.refresh()

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key in ("t", "T"):
            self._edit_root()
            return None
        if key == "f10":
            self._apply()
            return None
        return key

    def _edit_root(self) -> None:
        entry = urwid.Edit("Target root: ", self._root)

        def save():
            root = entry.edit_text.strip()
            if not mount.valid_target_root(root):
                self.app.notify(
                    "Target root must be under /mnt, /media or /run/media.", error=True)
                return
            self._root = root
            self.app.pop()
            self._rederive()

        modal = Modal(
            self.app, "Install target root",
            [urwid.Text(("hint", "Where the new system is assembled (e.g. /mnt/gentoo).")),
             urwid.Divider(), entry],
            [("Save", save), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 70), height=("relative", 45))

    def _apply(self) -> None:
        if self._plan is None:
            self.app.notify("Set a valid target root first (press 't').", error=True)
            return
        if not self._plan.mounts:
            self.app.notify("Nothing to mount in this plan.", error=True)
            return
        self.app.push(MountApplyScreen(self.app, self._plan))


class MountApplyScreen(Screen):
    """Stream the mount pipeline, then generate and (optionally) write the fstab."""

    def __init__(self, app: App, plan: MountPlan) -> None:
        self._plan = plan
        self._done = False
        self._fstab_text = ""
        self._executor = choose_executor()
        self._direct = isinstance(self._executor, DirectExecutor)
        self._labels = ([s.label for s in mount.mount_steps(plan)] if self._direct
                        else mount.mount_plan_labels(plan))
        self._total = len(self._labels)
        self._phase = urwid.Text(("field", " Preparing …"))
        self._bar = urwid.ProgressBar("pb_normal", "pb_complete", 0, max(self._total, 1))
        self._log_walker = urwid.SimpleFocusListWalker([])
        self._log = urwid.ListBox(self._log_walker)
        body = urwid.Pile([
            ("pack", urwid.AttrMap(self._phase, "field")),
            ("pack", urwid.Divider("─")),
            ("pack", self._bar),
            ("pack", urwid.Divider("─")),
            ("weight", 1, boxed(self._log, title="Output")),
        ])
        super().__init__(app, body, title="Mounting Install Target",
                         footer_keys=[("Esc", "Back")])
        app.run_async(self._run())

    def _log_lines(self, lines: list[str]) -> None:
        for ln in lines:
            self._log_walker.append(urwid.Text(strip_ansi(ln)))
        del self._log_walker[:-500]
        with contextlib.suppress(Exception):
            self._log_walker.set_focus(len(self._log_walker) - 1)
        self.app.refresh()

    def _on_step(self, index: int) -> None:
        self._bar.set_completion(min(index, self._total))
        if 0 <= index < self._total:
            self._phase.set_text(("field", f" {self._labels[index]}"))
        self.app.refresh()

    async def _run(self) -> None:
        def on_progress(lines: list[str]) -> None:
            self._log_lines(lines)

        try:
            if self._direct:
                await mount.apply_mount_plan(
                    self._plan, self._executor, on_progress=on_progress, on_step=self._on_step)
            else:
                backend = DiskBackend()
                try:
                    await backend.connect()
                    await mount.apply_mount_plan_via_backend(
                        self._plan, backend, on_progress=on_progress, on_step=self._on_step)
                finally:
                    with contextlib.suppress(Exception):
                        await backend.close()
        except StepError as exc:
            self._finish_mount(False, f"{exc.step.label} failed:\n{exc.result.output}")
            return
        except Exception as exc:
            self._finish_mount(False, str(exc))
            return
        await self._after_mount()

    async def _after_mount(self) -> None:
        """Mount succeeded — read UUIDs and generate the target's fstab."""
        self._bar.set_completion(self._total)
        self._phase.set_text(("ok", " mounted — generating fstab"))
        try:
            uuids = {}
            for dev in mount.fstab_devices(self._plan):
                uuids[dev] = await self.app.run_blocking(
                    lambda d=dev: reader.device_uuid(d))
            self._fstab_text = mount.generate_target_fstab(self._plan, uuids)
        except Exception as exc:
            self._finish_mount(True, f"Mounted, but could not generate fstab: {exc}",
                               fstab_ok=False)
            return
        self._log_lines(["", f"# generated {self._plan.root}/etc/fstab:", ""])
        self._log_lines(self._fstab_text.splitlines())
        self._offer_fstab()

    def _offer_fstab(self) -> None:
        def write():
            self.app.pop()
            self.app.run_async(self._write_fstab())

        def skip():
            self.app.pop()
            self._final(True, f"Mounted at {self._plan.root} (fstab not written).")

        modal = Modal(
            self.app, "Write /etc/fstab",
            [urwid.Text(f"Filesystems mounted under {self._plan.root}."),
             urwid.Divider(),
             urwid.Text(f"Write the generated fstab to {self._plan.root}/etc/fstab?")],
            [("Write fstab", write), ("Skip", skip)],
        )
        self.app.push_modal(modal, width=("relative", 66), height=("relative", 46))

    async def _write_fstab(self) -> None:
        try:
            if self._direct:
                path = await self.app.run_blocking(
                    lambda: mount.write_target_fstab_file(self._plan.root, self._fstab_text))
                out = f"wrote {path}"
            else:
                backend = DiskBackend()
                try:
                    await backend.connect()
                    ok, out = await backend.write_target_fstab(
                        self._plan.root, self._fstab_text)
                finally:
                    with contextlib.suppress(Exception):
                        await backend.close()
                if not ok:
                    self._final(False, f"fstab write failed:\n{out}")
                    return
        except Exception as exc:
            self._final(False, f"fstab write failed: {exc}")
            return
        self._final(True, f"Install target ready at {self._plan.root}.\n{out}")

    def _finish_mount(self, ok: bool, message: str, *, fstab_ok: bool = True) -> None:
        if ok and not fstab_ok:
            self._final(True, message)
            return
        self._final(ok, message)

    def _final(self, ok: bool, message: str) -> None:
        self._done = True
        self._phase.set_text(("ok" if ok else "error", " done" if ok else " failed"))
        self.app.notify("done" if ok else "failed", error=not ok)

        def back():
            self.app.pop()      # result modal
            self.app.pop()      # this screen → back to the target picker

        def to_menu():
            self.app.pop()
            self.app.pop_to_root()

        modal = Modal(
            self.app, "Install target ready" if ok else "Mount failed",
            [urwid.Text(("ok" if ok else "error", message))],
            [("Back", back), ("Main menu", to_menu)],
        )
        self.app.push_modal(modal, width=("relative", 68), height=("relative", 48))
        self.app.refresh()

    def handle_key(self, key):
        if key == "esc":
            if self._done:
                self.app.pop()
            return None
        return key
