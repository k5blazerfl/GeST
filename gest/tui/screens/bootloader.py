"""Bootloader & kernel (urwid): show kernel/bootloader info, regenerate GRUB,
install GRUB (UEFI or BIOS).

Info is read unprivileged. Regenerating goes through the polkit-gated backend.
Installing picks its path by runtime (``core.exec.choose_executor``): in-process
when running as root (live CD), else the polkit-gated backend — so the same flow
works from the installer environment and on a running system.
"""

from __future__ import annotations

import contextlib

import urwid

from gest.core.bootloader import install, reader
from gest.core.bootloader.backend_client import BootloaderBackend
from gest.core.exec.executor import DirectExecutor
from gest.core.exec.select import choose_executor
from gest.core.exec.steps import StepError
from gest.tui.runtime import App, Modal, Screen, boxed, strip_ansi


class BootloaderScreen(Screen):
    def __init__(self, app: App) -> None:
        self._bootloader = "unknown"
        self._info = urwid.Text(" loading …")
        self._log_walker = urwid.SimpleFocusListWalker(
            [urwid.Text("Press r to regenerate the config, or i to install GRUB.")]
        )
        self._log = urwid.ListBox(self._log_walker)
        pile = urwid.Pile([
            ("pack", self._info),
            ("pack", urwid.Divider()),
            ("weight", 1, boxed(self._log, title="Output")),
        ])
        super().__init__(
            app, pile, title="Bootloader & Kernel",
            footer_keys=[("r", "Regenerate GRUB"), ("i", "Install GRUB"), ("Esc", "Back")],
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        info = await self.app.run_blocking(reader.boot_info)
        self._bootloader = info.bootloader
        self._info.set_text("\n".join([
            f" Running kernel : {info.running_kernel}",
            f" Kernel source  : {info.kernel_source or '—'}",
            f" Bootloader     : {info.bootloader}",
            f" GRUB config    : {info.grub_cfg}",
            f" Installed      : {', '.join(info.kernels) or '—'}",
        ]))
        self.app.refresh()

    def _log_lines(self, lines: list[str]) -> None:
        for ln in lines:
            self._log_walker.append(urwid.Text(strip_ansi(ln)))
        del self._log_walker[:-500]
        with contextlib.suppress(Exception):
            self._log_walker.set_focus(len(self._log_walker) - 1)
        self.app.refresh()

    async def _regen(self) -> None:
        self._log_walker[:] = [urwid.Text("Regenerating bootloader config … please wait.")]
        self.app.refresh()
        backend = BootloaderBackend()
        try:
            await backend.connect()
            ok, out = await backend.regenerate_grub()
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        lines = out.splitlines() or ["(no output)"]
        self._log_walker[:] = [urwid.SelectableIcon(line, 0) for line in lines]
        self._log_walker.set_focus(0)
        self.app.notify("bootloader config regenerated" if ok else "regeneration failed",
                        error=not ok)

    # -- install ------------------------------------------------------------

    def _configure_install(self) -> None:
        firmware_group: list = []
        uefi_rb = urwid.RadioButton(firmware_group, "UEFI  (x86_64-efi)")
        urwid.RadioButton(firmware_group, "BIOS / legacy  (i386-pc)")
        efi = urwid.Edit("EFI directory   : ", "/efi")
        boot_id = urwid.Edit("Bootloader ID   : ", "GRUB")
        disk = urwid.Edit("BIOS disk       : ", "")
        removable = urwid.CheckBox("Removable install (--removable)")

        def start():
            firmware = "uefi" if uefi_rb.state else "bios"
            config = install.InstallConfig(
                firmware=firmware,
                efi_directory=efi.edit_text.strip() or "/efi",
                bootloader_id=boot_id.edit_text.strip() or "GRUB",
                removable=removable.state,
                disk=disk.edit_text.strip(),
            )
            try:
                install.install_steps(config)          # validate before we commit
            except ValueError as exc:
                self.app.notify(str(exc), error=True)
                return
            self.app.pop()
            self.app.run_async(self._install(config))

        modal = Modal(
            self.app, "Install GRUB",
            [urwid.Text(("hint", "UEFI needs the ESP mounted at the EFI directory; "
                                 "BIOS writes boot code to the disk's MBR.")),
             urwid.Divider(), uefi_rb, firmware_group[1],
             urwid.Divider(), efi, boot_id, disk, removable],
            [("Install", start), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 74), height=("relative", 66))

    async def _install(self, config: install.InstallConfig) -> None:
        self._log_walker[:] = [urwid.Text(f"Installing GRUB ({config.firmware}) …")]
        self.app.refresh()
        executor = choose_executor()
        try:
            if isinstance(executor, DirectExecutor):
                await install.install(config, executor, on_progress=self._log_lines)
            else:
                backend = BootloaderBackend()
                try:
                    await backend.connect()
                    await install.install_via_backend(
                        config, backend, on_progress=self._log_lines)
                finally:
                    with contextlib.suppress(Exception):
                        await backend.close()
        except StepError as exc:
            self._log_lines(exc.result.output.splitlines())
            self.app.notify(f"{exc.step.label} failed", error=True)
            return
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            return
        self.app.notify("bootloader installed", error=False)

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key == "r":
            if self._bootloader != "grub":
                self.app.notify("Only GRUB regeneration is supported.", error=True)
            else:
                self.app.run_async(self._regen())
            return None
        if key in ("i", "I"):
            self._configure_install()
            return None
        return key
