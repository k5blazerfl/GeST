"""Disks & mounts (urwid): block-device tree + /etc/fstab editor.

Reading is unprivileged (`lsblk`, /etc/fstab); mounting and fstab writes go
through the polkit-gated DiskBackend. Protected mounts (/, /boot, /efi, swap)
are shown read-only.
"""

from __future__ import annotations

import contextlib

import urwid

from gest.core.disk import fstab, reader
from gest.core.disk.backend_client import DiskBackend
from gest.core.disk.fstab import FstabEntry
from gest.core.disk.model import BlockDevice
from gest.tui.runtime import App, Modal, NavPile, Screen, boxed


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


def _dev_rows(devices: list[BlockDevice], depth: int = 0) -> list[urwid.Widget]:
    rows: list[urwid.Widget] = []
    for dev in devices:
        indent = "  " * depth
        mp = f"  → {dev.mountpoint}" if dev.mountpoint else ""
        rows.append(urwid.Text(
            f"{indent}{dev.name:<18}{dev.size:>9}  {dev.type:<6} {dev.fstype or '—':<8}{mp}"))
        rows.extend(_dev_rows(dev.children, depth + 1))
    return rows


class DiskScreen(Screen):
    def __init__(self, app: App) -> None:
        self._entries: list[FstabEntry] = []
        self._dev_walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._dev_list = urwid.ListBox(self._dev_walker)
        self._fstab_walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._fstab_list = urwid.ListBox(self._fstab_walker)
        self._pile = NavPile([
            (12, boxed(self._dev_list, title="Block Devices")),
            boxed(self._fstab_list, title="/etc/fstab  (🔒 = protected)"),
        ])
        super().__init__(
            app, self._pile, title="Disks & Mounts",
            footer_keys=[
                ("m", "Mount"), ("u", "Unmount"), ("a", "Add"),
                ("e", "Edit"), ("d", "Remove"), ("Esc", "Back"),
            ],
        )
        self.configure_pane_cycle(self._pile, [0, 1])   # Tab switches panes
        app.run_async(self._load())

    def _footer_context(self):
        if self._pile.focus_position == 0:              # Block Devices (info)
            return [("Tab", "fstab"), ("Esc", "Back")]
        return [("m", "Mount"), ("u", "Unmount"), ("a", "Add"), ("e", "Edit"),
                ("d", "Remove"), ("Tab", "Devices"), ("Esc", "Back")]

    async def _load(self) -> None:
        devices = await self.app.run_blocking(reader.list_block_devices)
        entries = await self.app.run_blocking(reader.read_fstab)
        self._entries = entries
        self._dev_walker[:] = _dev_rows(devices) or [urwid.Text(" (no devices)")]
        prev = self._fstab_walker.focus if self._entries else 0
        rows = [
            _row(f"{'🔒' if e.protected else '  '} {e.mountpoint:<22} "
                 f"{e.spec:<26} {e.fstype:<8} {e.options}")
            for e in entries
        ] or [urwid.Text(" (no fstab entries)")]
        self._fstab_walker[:] = rows
        if entries:
            self._fstab_walker.set_focus(min(prev or 0, len(entries) - 1))
        with contextlib.suppress(Exception):
            self._pile.focus_position = 1  # land on the fstab list
        self._refresh_footer()
        self.app.refresh()

    def _current(self) -> FstabEntry | None:
        if not self._entries:
            return None
        idx = self._fstab_walker.focus
        if idx is None or not 0 <= idx < len(self._entries):
            return None
        return self._entries[idx]

    async def _call(self, action, reload: bool = True) -> None:
        backend = DiskBackend()
        try:
            await backend.connect()
            ok, out = await action(backend)
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        self.app.notify(out or ("done" if ok else "failed"), error=not ok)
        if reload:
            await self._load()

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        entry = self._current()
        if key in ("m", "u"):
            if entry is None:
                return None
            if not fstab.valid_mount_target(entry.mountpoint):
                self.app.notify("Not a mountable entry (e.g. swap).", error=True)
                return None
            mp = entry.mountpoint
            action = (lambda b: b.mount(mp)) if key == "m" else (lambda b: b.unmount(mp))
            self.app.run_async(self._call(action, reload=False))
            return None
        if key == "a":
            self._form(None)
            return None
        if key == "e":
            if entry is None:
                return None
            if entry.protected:
                self.app.notify("Protected mount — not editable.", error=True)
                return None
            self._form(entry)
            return None
        if key == "d":
            if entry is None:
                return None
            if entry.protected:
                self.app.notify("Protected mount — can't be removed.", error=True)
                return None
            self._confirm_remove(entry)
            return None
        return key

    def _form(self, entry: FstabEntry | None) -> None:
        editing = entry is not None
        spec = urwid.Edit("Device / UUID= : ", entry.spec if editing else "")
        fstype = urwid.Edit("Filesystem     : ", entry.fstype if editing else "")
        options = urwid.Edit("Options        : ", entry.options if editing else "defaults")
        # Mount point is fixed when editing (so upsert replaces the right line),
        # editable when adding.
        mp_edit = None if editing else urwid.Edit("Mount point    : ", "")
        mp_widget: urwid.Widget = (
            urwid.Text(f"Mount point    : {entry.mountpoint}") if editing else mp_edit
        )

        def save():
            mountpoint = entry.mountpoint if editing else mp_edit.edit_text.strip()
            new = FstabEntry(
                spec.edit_text.strip(), mountpoint,
                fstype.edit_text.strip(), options.edit_text.strip() or "defaults",
            )
            if not fstab.valid_entry(new):
                self.app.notify("Invalid entry (check device, mount point, fs, options).",
                                error=True)
                return
            if fstab.is_protected(new):
                self.app.notify("That mount point is protected.", error=True)
                return
            self.app.pop()
            self.app.run_async(self._call(lambda b: b.write_fstab_entry(
                new.spec, new.mountpoint, new.fstype, new.options)))

        title = f"Edit {entry.mountpoint}" if editing else "Add fstab entry"
        modal = Modal(
            self.app, title,
            [mp_widget, spec, fstype, options],
            [("Save", save), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 70), height=("relative", 55))

    def _confirm_remove(self, entry: FstabEntry) -> None:
        def do_remove():
            self.app.pop()
            self.app.run_async(self._call(lambda b: b.remove_fstab_entry(entry.mountpoint)))

        modal = Modal(
            self.app, "Remove fstab entry",
            [urwid.Text(f"Remove the entry for {entry.mountpoint}?"),
             urwid.Text(("hint", "A backup is written to /etc/fstab.gest.bak."))],
            [("Remove", do_remove), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 60))
