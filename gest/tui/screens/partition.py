"""Partition a disk (urwid): pick a target, configure a UEFI layout, review the
diff, type-to-confirm the wipe, then apply with streaming progress.

The dangerous logic (device safety, the ordered pipeline) lives in
``core/disk/provision``; this screen only builds a ``DiskPlan`` and drives it.
Applying picks its path by runtime (``core.exec.choose_executor``): in-process on
a live CD running as root, or the polkit-gated backend on an installed system —
the screen is agnostic to which.
"""

from __future__ import annotations

import contextlib

import urwid

from gest.core.disk import commands, provision, reader
from gest.core.disk.backend_client import DiskBackend
from gest.core.disk.model import BlockDevice, DiskPlan
from gest.core.exec.executor import DirectExecutor
from gest.core.exec.select import choose_executor
from gest.tui.runtime import App, Modal, NavPile, Screen, boxed, strip_ansi


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


class PartitionScreen(Screen):
    """Pick a disk, configure a layout, and launch the apply."""

    def __init__(self, app: App) -> None:
        self._devices: list[BlockDevice] = []
        self._disks: list[BlockDevice] = []
        self._mounts = ""
        self._root_src: str | None = None
        self._plan: DiskPlan | None = None
        self._disk_walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._disk_list = urwid.ListBox(self._disk_walker)
        self._plan_walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._plan_list = urwid.ListBox(self._plan_walker)
        self._pile = NavPile([
            (10, boxed(self._disk_list, title="Target Disk")),
            boxed(self._plan_list, title="Planned Layout  (⚠ ERASES the disk)"),
        ])
        super().__init__(
            app, self._pile, title="Partition Disks",
            footer_keys=[("c", "Configure layout"), ("F10", "Apply"), ("Esc", "Back")],
        )
        self.configure_pane_cycle(self._pile, [0, 1])
        app.run_async(self._load())

    async def _load(self) -> None:
        self._devices = await self.app.run_blocking(reader.list_block_devices)
        self._mounts = await self.app.run_blocking(reader.read_proc_mounts)
        self._root_src = provision.root_source(self._mounts)
        self._disks = [d for d in self._devices if d.type == "disk"]
        rows = []
        for dev in self._disks:
            flag = "  ⚠ running system" if self._holds_root(dev) else ""
            rows.append(_row(f"{dev.name:<16}{dev.size:>10}   {dev.type}{flag}"))
        self._disk_walker[:] = rows or [urwid.Text(" (no disks found)")]
        self._render_plan()
        self.app.refresh()

    def _holds_root(self, dev: BlockDevice) -> bool:
        path = f"/dev/{dev.name}"
        return bool(self._root_src) and (
            self._root_src == path or self._root_src.startswith(path))

    def _selected_disk(self) -> BlockDevice | None:
        if not self._disks:
            return None
        idx = self._disk_walker.focus
        if idx is None or not 0 <= idx < len(self._disks):
            return None
        return self._disks[idx]

    def _render_plan(self) -> None:
        if self._plan is None:
            self._plan_walker[:] = [
                urwid.Text(" No layout yet — select a disk and press 'c' to configure.")]
            return
        rows: list[urwid.Widget] = [
            urwid.Text(("error", f" Target {self._plan.disk} — all existing data is erased.")),
            urwid.Divider("─"),
            urwid.Text(("pane_title", "  Partitions")),
        ]
        for part in self._plan.partitions:
            rows.append(urwid.Text(
                f"    {part.number}  {part.size:>6}  {part.type_guid}  {part.label or ''}"))
        rows.append(urwid.Divider("─"))
        rows.append(urwid.Text(("pane_title", "  Filesystems")))
        for fs in self._plan.filesystems:
            rows.append(urwid.Text(("dim", f"    {fs.kind:<6} {fs.device}  {fs.label or ''}")))
        self._plan_walker[:] = rows

    def _footer_context(self):
        if self._pile.focus_position == 0:
            return [("c", "Configure layout"), ("F10", "Apply"), ("Tab", "Layout"),
                    ("Esc", "Back")]
        return [("c", "Configure layout"), ("F10", "Apply"), ("Tab", "Disks"), ("Esc", "Back")]

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key in ("c", "C"):
            self._configure()
            return None
        if key == "f10":
            self._apply()
            return None
        return key

    def _configure(self) -> None:
        disk = self._selected_disk()
        if disk is None:
            self.app.notify("Select a target disk first.", error=True)
            return
        if self._holds_root(disk):
            self.app.notify("That disk holds the running system — refused.", error=True)
            return
        esp = urwid.Edit("EFI system partition size : ", "512M")
        swap = urwid.Edit("Swap size (blank = none)  : ", "")
        root_fs = urwid.Edit("Root filesystem           : ", "ext4")

        def save():
            try:
                plan = provision.uefi_plan(disk.name, esp.edit_text.strip(),
                                           swap.edit_text.strip(), root_fs.edit_text.strip())
            except ValueError as exc:
                self.app.notify(str(exc), error=True)
                return
            self._plan = plan
            self.app.pop()
            self._render_plan()
            self.app.refresh()

        modal = Modal(
            self.app, f"Configure layout — {disk.name}",
            [urwid.Text(("hint", "GPT/UEFI: ESP + optional swap + root (fills the rest).")),
             urwid.Text(("hint", f"Root filesystem one of: "
                                  f"{', '.join(sorted(commands.ROOT_FS_KINDS))}.")),
             urwid.Divider(), esp, swap, root_fs],
            [("Save", save), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 72), height=("relative", 60))

    def _apply(self) -> None:
        if self._plan is None:
            self.app.notify("Configure a layout first (press 'c').", error=True)
            return
        problems = provision.validate_plan(self._plan, self._devices, self._mounts)
        if problems:
            self.app.notify(problems[0], error=True)
            return
        self._confirm()

    def _confirm(self) -> None:
        assert self._plan is not None
        disk = self._plan.disk
        name = disk.rsplit("/", 1)[-1]
        entry = urwid.Edit("Type the disk name to confirm: ")

        def go():
            if entry.edit_text.strip() != name:
                self.app.notify(f"Type '{name}' exactly to confirm.", error=True)
                return
            self.app.pop()      # confirm modal
            self.app.push(PartitionApplyScreen(
                self.app, self._plan, self._devices, self._mounts))

        modal = Modal(
            self.app, "Erase and partition",
            [urwid.Text(("error", f" This ERASES ALL DATA on {disk}.")),
             urwid.Divider(),
             urwid.Text("Every partition and filesystem on the disk is destroyed."),
             urwid.Divider(), entry],
            [("Erase & Apply", go), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 66), height=("relative", 50))


class PartitionApplyScreen(Screen):
    """Run a `DiskPlan` and stream progress; the executor is chosen by runtime."""

    def __init__(self, app: App, plan: DiskPlan, devices: list[BlockDevice],
                 mounts: str) -> None:
        self._plan = plan
        self._devices = devices
        self._mounts = mounts
        self._done = False
        self._executor = choose_executor()
        self._direct = isinstance(self._executor, DirectExecutor)
        self._labels = ([s.label for s in provision.plan_steps(plan)] if self._direct
                        else provision.plan_phase_labels(plan))
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
        super().__init__(app, body, title="Partitioning",
                         footer_keys=[("Esc", "Back")])
        app.run_async(self._run())

    def _log_lines(self, lines: list[str]) -> None:
        for ln in lines:
            self._log_walker.append(urwid.Text(strip_ansi(ln)))
        del self._log_walker[:-500]                 # cap the buffer
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
                await provision.apply_plan(
                    self._plan, self._executor, self._devices, self._mounts,
                    on_progress=on_progress, on_step=self._on_step)
            else:
                backend = DiskBackend()
                try:
                    await backend.connect()
                    await provision.apply_via_backend(
                        self._plan, backend, on_progress=on_progress, on_step=self._on_step)
                finally:
                    with contextlib.suppress(Exception):
                        await backend.close()
        except provision.DiskSafetyError as exc:
            self._finish(False, f"Refused: {exc}")
            return
        except provision.DiskApplyError as exc:
            self._finish(False, f"{exc.step.label} failed:\n{exc.result.output}")
            return
        except Exception as exc:
            self._finish(False, str(exc))
            return
        self._finish(True, f"{self._plan.disk} partitioned and formatted.")

    def _finish(self, ok: bool, message: str) -> None:
        self._done = True
        self._bar.set_completion(self._total if ok else self._bar.current)
        self._phase.set_text(("ok" if ok else "error", " done" if ok else " failed"))
        self.app.notify("done" if ok else "failed", error=not ok)

        def back():
            self.app.pop()      # result modal
            self.app.pop()      # this screen → back to the picker

        def to_menu():
            self.app.pop()
            self.app.pop_to_root()

        def mount_target():
            from gest.tui.screens.mount_target import MountTargetScreen
            self.app.pop()      # result modal
            self.app.pop()      # this apply screen → back to the picker
            self.app.push(MountTargetScreen(
                self.app, self._plan, self._devices, self._mounts))

        # On success, offer to continue into assembling the install target.
        buttons = ([("Mount as install target", mount_target)] if ok else []) + \
            [("Back", back), ("Main menu", to_menu)]
        modal = Modal(
            self.app, "Partitioning complete" if ok else "Partitioning failed",
            [urwid.Text(("ok" if ok else "error", message))],
            buttons,
        )
        self.app.push_modal(modal, width=("relative", 66), height=("relative", 50))
        self.app.refresh()

    def handle_key(self, key):
        if key == "esc":
            if self._done:                          # never abandon a run mid-flight
                self.app.pop()
            return None
        return key
