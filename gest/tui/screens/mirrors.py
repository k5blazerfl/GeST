"""Main-repository mirror picker (urwid).

Reached from Software Repositories with the ★ main repo focused (key m). Lists
Gentoo's official rsync rotations — the current one flagged ★ — plus a Custom…
entry for any rsync URI. Choosing one rewrites the main repo's ``sync-uri`` in
``/etc/portage/repos.conf/gentoo.conf`` via the Portage backend (root), keeping
every other setting (location, verification keys), then returns to the list.
"""

from __future__ import annotations

import contextlib
import os

import urwid

from gest.core.portage.backend_client import PortageBackend
from gest.core.portage.write import ConfigWrite
from gest.core.repos import commands, mirrors
from gest.tui.runtime import App, Modal, Screen, boxed


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _row(text: str, attr: str | None = None) -> urwid.Widget:
    icon = urwid.SelectableIcon(text, 0)
    icon.set_wrap_mode("clip")
    return urwid.AttrMap(icon, attr, focus_map="focus")


class MirrorScreen(Screen):
    """Pick the rsync mirror the main repository syncs from."""

    def __init__(self, app: App, *, repo: str, current: str = "", on_done=None):
        self._repo = repo
        self._current = current.strip()
        self._on_done = on_done
        # (label, uri | None) — None marks the Custom… action.
        self._entries: list[tuple[str, str | None]] = [
            *mirrors.mirrors(), ("Custom rsync URI …", None)]

        self._walker = urwid.SimpleFocusListWalker([])
        self._list = urwid.ListBox(self._walker)
        self._status = urwid.Text("")
        body = urwid.Pile([
            ("pack", urwid.AttrMap(
                urwid.Text(f" Current: {self._current or '— (Portage default)'}",
                           wrap="clip"), "field")),
            ("pack", urwid.Divider("─")),
            ("weight", 1, boxed(self._list, title="rsync mirrors")),
            ("pack", self._status),
        ])
        super().__init__(
            app, body, title="Main Repository Mirror",
            footer_keys=[("Enter", "Use mirror"), ("Esc", "Back")],
            help_text=(
                "Choose the rsync mirror the main ::gentoo tree syncs from. A\n"
                "mirror geographically near you makes emerge --sync faster.\n\n"
                "The current mirror is flagged ★. Enter sets the highlighted one\n"
                "(or Custom… to type any rsync URI); only sync-uri changes —\n"
                "location and the OpenPGP verification settings are preserved.\n"
                "Applying writes /etc/portage/repos.conf/gentoo.conf as root."))
        self._rebuild()

    def _rebuild(self) -> None:
        rows = []
        for label, uri in self._entries:
            if uri is None:
                rows.append(_row(f"  {label}", "hint"))
                continue
            mark = "★" if uri == self._current else " "
            host = uri.replace("rsync://", "").replace("/gentoo-portage", "")
            rows.append(_row(f"{mark} {label:<26} {host}",
                             "ok" if mark == "★" else None))
        self._walker[:] = rows
        self._walker.set_focus(0)

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key == "enter":
            _label, uri = self._entries[self._walker.focus]
            if uri is None:
                self._prompt_custom()
            else:
                self._choose(uri)
            return None
        return key

    def _prompt_custom(self) -> None:
        edit = urwid.Edit("rsync URI: ", self._current or "rsync://")

        def save():
            uri = edit.edit_text.strip()
            if not commands.valid_uri(uri):
                self.app.notify("Enter a valid rsync URI.", error=True)
                return
            self.app.pop()
            self._choose(uri)

        modal = Modal(self.app, "Custom rsync mirror", [edit],
                      [("Use", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 70), height=("relative", 40))

    def _choose(self, uri: str) -> None:
        if uri == self._current:
            self.app.notify("That is already the current mirror.")
            return
        self._status.set_text(("field", f" Setting mirror to {uri} …"))
        self.app.refresh()
        self.app.run_async(self._apply(uri))

    async def _apply(self, uri: str) -> None:
        path = mirrors.gentoo_conf_path()
        text = await self.app.run_blocking(_read_text, path)
        content = mirrors.set_sync_uri(text, self._repo, uri)
        backend = PortageBackend()
        ok = False
        try:
            await backend.connect()
            ok = await backend.write_config([ConfigWrite(path, content)])
        except Exception as exc:
            with contextlib.suppress(Exception):
                await backend.close()
            self._status.set_text(("error", f" Could not set the mirror: {exc}"))
            self.app.refresh()
            return
        await backend.close()
        if not ok:
            self._status.set_text(
                ("error", " Could not set the mirror — the write was rejected."))
            self.app.refresh()
            return
        self.app.notify(f"Main repository mirror set to {os.path.basename(path)}.")
        if self._on_done is not None:
            with contextlib.suppress(Exception):
                self._on_done()
        self.app.pop()
