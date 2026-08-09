"""License acceptance editor (urwid): per-package licenses + global ACCEPT_LICENSE.

Reading is unprivileged; changes go through the polkit-gated Portage backend
(WriteConfig → portage.configure). GeST edits its own package.license/gest and
the ACCEPT_LICENSE variable in make.conf; entries from other fragments are
shown read-only.
"""

from __future__ import annotations

import urwid

from gest.core.licenses import reader, writer
from gest.core.licenses.model import LicenseEntry
from gest.core.portage.backend_client import PortageBackend
from gest.tui.runtime import App, Modal, Screen

_HEADER_ROWS = 2  # global ACCEPT_LICENSE line + a divider precede the list


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


class LicensesScreen(Screen):
    def __init__(self, app: App) -> None:
        self._entries: list[LicenseEntry] = []
        self._accept = ""
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, urwid.LineBox(self._list, title="License acceptance"),
            title="Licenses",
            footer_keys=[
                ("A", "Add"), ("Enter", "Edit"), ("x", "Remove"),
                ("g", "Global"), ("Esc", "Back"),
            ],
            help_text=(
                "Accept licenses so restricted packages can be installed.\n\n"
                "A     add a per-package acceptance to package.license/gest\n"
                "Enter/e   edit the highlighted (managed) acceptance\n"
                "x     remove the highlighted managed acceptance\n"
                "g     edit the global ACCEPT_LICENSE in make.conf\n\n"
                "Per-package example:  app-arch/unrar unRAR\n"
                "Groups (for ACCEPT_LICENSE):  @FREE  @BINARY-REDISTRIBUTABLE\n"
                "Entries from other package.license fragments are read-only."
            ),
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        self._entries = await self.app.run_blocking(reader.read_all)
        self._accept = await self.app.run_blocking(reader.accept_license)
        self._render()
        self.app.refresh()

    def _render(self) -> None:
        rows: list[urwid.Widget] = [
            urwid.Text(f"  ACCEPT_LICENSE = {self._accept or '(unset)'}   (g to edit)"),
            urwid.Divider("─"),
        ]
        if self._entries:
            for e in self._entries:
                tag = " " if e.managed else "·"  # · = external (read-only)
                rows.append(_row(f"{tag} {e.atom:<28} {' '.join(e.licenses)}"))
        else:
            rows.append(urwid.Text("  (no per-package acceptances — press A to add one)"))
        focus = self._walker.focus if self._walker else _HEADER_ROWS
        self._walker[:] = rows
        self._walker.set_focus(min(max(focus, _HEADER_ROWS), len(rows) - 1))

    def _current(self) -> LicenseEntry | None:
        idx = self._walker.focus - _HEADER_ROWS
        if self._entries and 0 <= idx < len(self._entries):
            return self._entries[idx]
        return None

    def handle_key(self, key):
        entry = self._current()
        if key == "esc":
            self.app.pop()
        elif key == "A":
            self._edit_modal(None)
        elif key in ("enter", "e") and entry is not None:
            if entry.managed:
                self._edit_modal(entry)
            else:
                self.app.notify("That entry is external (read-only here).", error=True)
        elif key == "x" and entry is not None:
            if entry.managed:
                self._confirm_remove(entry.atom)
            else:
                self.app.notify("That entry is external (read-only here).", error=True)
        elif key == "g":
            self._global_modal()
        else:
            return key
        return None

    # -- backend plumbing ---------------------------------------------------

    async def _write(self, build) -> None:
        """Build a ConfigWrite off the main loop and apply it, then reload."""
        write = await self.app.run_blocking(build)
        backend = PortageBackend()
        try:
            await backend.connect()
            ok = await backend.write_config([write])
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        if not ok:
            self.app.notify("change was not applied", error=True)
        await self._load()

    # -- modals -------------------------------------------------------------

    def _edit_modal(self, entry: LicenseEntry | None) -> None:
        atom = urwid.Edit("Package atom: ", entry.atom if entry else "")
        licenses = urwid.Edit("Licenses: ", " ".join(entry.licenses) if entry else "")

        def save():
            a = atom.edit_text.strip()
            toks = licenses.edit_text.split()
            if "/" not in a or " " in a:
                self.app.notify("A package atom like cat/pkg is required.", error=True)
                return
            if not toks:
                self.app.notify("At least one license (or * ) is required.", error=True)
                return
            self.app.pop()
            self.app.run_async(self._write(lambda: writer.set_licenses(a, toks)))

        title = f"Edit licenses for {entry.atom}" if entry else "Accept a package's licenses"
        modal = Modal(self.app, title,
                      [atom, licenses, urwid.Divider(),
                       urwid.Text("e.g.  app-arch/unrar unRAR   ·   * accepts any")],
                      [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 80), height=("relative", 55))

    def _global_modal(self) -> None:
        value = urwid.Edit("ACCEPT_LICENSE: ", self._accept)

        def save():
            self.app.pop()
            self.app.run_async(
                self._write(lambda: writer.set_accept_license(value.edit_text.strip())))

        modal = Modal(self.app, "Global ACCEPT_LICENSE (make.conf)",
                      [urwid.Text("Common: -* @FREE @BINARY-REDISTRIBUTABLE"),
                       urwid.Divider(), value],
                      [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 80), height=("relative", 55))

    def _confirm_remove(self, atom: str) -> None:
        def do():
            self.app.pop()
            self.app.run_async(self._write(lambda: writer.set_licenses(atom, [])))

        modal = Modal(self.app, f"Remove license acceptance for “{atom}”?", [],
                      [("Remove", do), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 65), height=("relative", 40))
