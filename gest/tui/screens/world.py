"""The @world set (urwid): review explicitly-installed packages and deselect.

The @world set is what you asked Portage for by name — everything else is a
dependency pulled in to satisfy it. This screen lists those explicit members
(Category · Package · Version) so you can *deselect* the ones you no longer want
tracked. Deselecting unmerges nothing: it only drops the package from @world so
a later Clean Up (depclean) may reclaim it once nothing else needs it.

Nothing is marked by default — deselecting is a deliberate act. Space marks a
package, F10 hands the marked atoms to ``emerge --deselect`` via the backend.
"""

from __future__ import annotations

import urwid

from gest.core.software import reader
from gest.core.software.backend_client import SoftwareBackend
from gest.core.software.model import Package
from gest.tui.runtime import App, Modal, NavPile, Screen, boxed, focusable_actions
from gest.tui.screens.runscreen import clip, row

_MARK_W = 2   # ✓ = will be dropped from @world
_CAT_W = 16
_PKG_W = 28
_VER_W = 18


def _fmt(mark: str, cat: str, pkg: str, ver: str) -> str:
    return (f"{mark:<{_MARK_W}}{clip(cat, _CAT_W):<{_CAT_W}}"
            f"{clip(pkg, _PKG_W):<{_PKG_W}}{clip(ver, _VER_W):<{_VER_W}}")


class WorldScreen(Screen):
    def __init__(self, app: App) -> None:
        self._members: list[Package] = []
        self._marked: set[str] = set()   # cp of packages to drop from @world
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)

        header = urwid.AttrMap(
            urwid.Text(_fmt("", "Category", "Package", "Version"), wrap="clip"),
            "pane_title")
        table = boxed(
            urwid.Pile([
                ("pack", header),
                ("pack", urwid.Divider("─")),
                ("weight", 1, self._list),
            ]),
            title="World set (explicitly installed)")

        self._count = urwid.Text("")
        self._actions = focusable_actions([
            ("Cancel", app.pop), ("Deselect", self._deselect)])
        body = NavPile([
            ("weight", 1, table),
            ("pack", self._count),
            ("pack", self._actions),
        ])
        super().__init__(
            app, body, title="World & Package Sets",
            footer_keys=[
                ("Space", "Mark"), ("a", "All"), ("n", "None"),
                ("F10", "Deselect"), ("Esc", "Back"),
            ],
            help_text=(
                "The @world set — the packages you installed explicitly (by name).\n"
                "Everything else Portage keeps only as a dependency.\n\n"
                "Deselecting a package removes it from @world but does NOT unmerge\n"
                "it. It simply stops being protected: the next Clean Up (depclean)\n"
                "may remove it once no other installed package needs it.\n\n"
                "Space  mark / unmark the highlighted package\n"
                "a      mark all        n  unmark all\n"
                "F10    deselect the marked packages (emerge --deselect)\n"
                "Esc    back"
            ),
        )
        self.configure_pane_cycle(body, [0], action_row=self._actions)
        app.run_async(self._load())

    def _footer_context(self):
        if self._on_action_row():
            return [("Enter", "Activate"), ("Tab", "Next"), ("Esc", "Back")]
        return self._base_footer_keys

    # -- loading / rendering ------------------------------------------------

    async def _load(self) -> None:
        pkgs = await self.app.run_blocking(reader.list_installed)
        self._members = sorted((p for p in pkgs if p.world_member),
                               key=lambda p: p.cp)
        self._marked &= {p.cp for p in self._members}   # drop stale marks
        self._rebuild()

    def _rebuild(self) -> None:
        focus = self._walker.focus or 0
        if not self._members:
            self._walker[:] = [urwid.Text(("dim", " The @world set is empty."))]
        else:
            self._walker[:] = [
                row(_fmt("✓" if p.cp in self._marked else "",
                         p.category, p.name, p.version),
                    None if p.cp in self._marked else "dim")
                for p in self._members]
            self._walker.set_focus(min(focus, len(self._members) - 1))
        self._refresh_count()
        self.app.refresh()

    def _refresh_count(self) -> None:
        total = len(self._members)
        marked = len(self._marked)
        if not total:
            self._count.set_text(("dim", " Nothing in @world"))
        elif not marked:
            self._count.set_text(("dim", f" {total} explicitly-installed packages"))
        else:
            self._count.set_text([
                ("ok", f" Deselect {marked} of {total}"),
                ("dim", "   ·   F10 Deselect"),
            ])

    # -- keys ---------------------------------------------------------------

    def _current(self) -> Package | None:
        if self._members and 0 <= self._walker.focus < len(self._members):
            return self._members[self._walker.focus]
        return None

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
        elif key == "r":
            self.app.run_async(self._load())
        elif key == " ":
            self._toggle()
        elif key == "a":
            self._marked = {p.cp for p in self._members}
            self._rebuild()
        elif key == "n":
            self._marked.clear()
            self._rebuild()
        elif key == "f10":
            self._deselect()
        else:
            return key
        return None

    def _toggle(self) -> None:
        pkg = self._current()
        if pkg is None:
            return
        self._marked.discard(pkg.cp) if pkg.cp in self._marked \
            else self._marked.add(pkg.cp)
        self._rebuild()

    # -- deselect -----------------------------------------------------------

    def _deselect(self) -> None:
        atoms = [p.cp for p in self._members if p.cp in self._marked]
        if not atoms:
            self.app.notify("Nothing marked to deselect.", error=True)
            return
        plural = "package" if len(atoms) == 1 else "packages"
        modal = Modal(
            self.app, f"Deselect {len(atoms)} {plural} from @world?",
            [urwid.Text(("hint",
                         "This unmerges nothing — it only removes them from the\n"
                         "@world set so a later Clean Up may reclaim them."))],
            [("Deselect", self._run), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 62))

    def _run(self) -> None:
        self.app.pop()   # the confirm modal
        atoms = [p.cp for p in self._members if p.cp in self._marked]
        self.app.run_async(self._call(atoms))

    async def _call(self, atoms: list[str]) -> None:
        backend = SoftwareBackend()
        try:
            await backend.connect()
            ok, out = await backend.deselect(atoms)
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        self.app.notify(
            out or (f"Deselected {len(atoms)}" if ok else "deselect failed"),
            error=not ok)
        if ok:
            self._marked.clear()
        await self._load()
