"""Bootloader & kernel (urwid): show kernel/bootloader info, regenerate GRUB.

Info is read unprivileged; regenerating the config goes through the polkit-gated
BootloaderBackend (`grub-mkconfig`).
"""

from __future__ import annotations

import urwid

from gest.core.bootloader import reader
from gest.core.bootloader.backend_client import BootloaderBackend
from gest.tui.runtime import App, Screen


class BootloaderScreen(Screen):
    def __init__(self, app: App) -> None:
        self._bootloader = "unknown"
        self._info = urwid.Text(" loading …")
        self._log_walker = urwid.SimpleFocusListWalker(
            [urwid.Text("Press r to regenerate the bootloader config.")]
        )
        self._log = urwid.ListBox(self._log_walker)
        pile = urwid.Pile([
            ("pack", self._info),
            ("pack", urwid.Divider()),
            ("weight", 1, urwid.LineBox(self._log, title="Output")),
        ])
        super().__init__(
            app, pile, title="Bootloader & Kernel",
            footer_keys=[("r", "Regenerate GRUB"), ("Esc", "Back")],
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
        return key
