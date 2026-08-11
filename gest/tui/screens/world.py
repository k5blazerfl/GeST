"""World & Package Sets (urwid): browse Portage sets; manage the world set.

A two-pane browser. The left pane lists the package sets — the **World set**
(the packages you installed explicitly), then Portage's built-in @system /
@profile, then any custom sets under /etc/portage/sets. The right pane shows the
members of whichever set is focused.

The World set is actionable: Space marks a package and F10 hands the marked
atoms to ``emerge --deselect`` (via the backend), dropping them from @world.
Deselecting unmerges nothing — it just removes the explicit-install record so a
later Clean Up (depclean) may reclaim them. Custom sets (/etc/portage/sets) are
editable too — create one (c), add/remove atoms (a / x) and delete it (d), all
written through the Portage backend. Portage's built-in @system / @profile are
read-only.
"""

from __future__ import annotations

import contextlib

import urwid

from gest.core.portage.backend_client import PortageBackend
from gest.core.portage.write import ConfigWrite
from gest.core.software import reader, sets
from gest.core.software.backend_client import SoftwareBackend
from gest.core.software.model import Package
from gest.core.software.sets import PackageSet
from gest.tui.runtime import App, Modal, NavPile, Screen, boxed, focusable_actions
from gest.tui.screens.runscreen import clip, row

_MARK_W = 2   # ✓ = will be dropped from @world
_CAT_W = 16
_PKG_W = 26
_VER_W = 16


def _fmt(mark: str, cat: str, pkg: str, ver: str) -> str:
    return (f"{mark:<{_MARK_W}}{clip(cat, _CAT_W):<{_CAT_W}}"
            f"{clip(pkg, _PKG_W):<{_PKG_W}}{clip(ver, _VER_W):<{_VER_W}}")


class WorldScreen(Screen):
    # Tab stops, in order (see _current_pane / _focus_pane / _cycle_pane).
    _PANES = ("sets", "members", "cancel", "deselect")

    def __init__(self, app: App) -> None:
        self._world_pkgs: list[Package] = []     # World-set members (markable)
        self._sets: list[PackageSet] = []        # the other, read-only sets
        self._marked: set[str] = set()           # cp of packages to deselect

        self._set_walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._set_list = urwid.ListBox(self._set_walker)
        left = boxed(self._set_list, title="Package sets")

        self._member_header = urwid.AttrMap(urwid.Text("", wrap="clip"), "pane_title")
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        right = boxed(
            urwid.Pile([
                ("pack", self._member_header),
                ("pack", urwid.Divider("─")),
                ("weight", 1, self._list),
            ]),
            title="Members")

        self._columns = urwid.Columns([(30, left), right], dividechars=1)
        self._count = urwid.Text("")
        self._actions = focusable_actions([
            ("Cancel", app.pop), ("Deselect", self._deselect)])
        self._pile = NavPile([
            ("weight", 1, self._columns),
            ("pack", self._count),
            ("pack", self._actions),
        ])
        super().__init__(
            app, self._pile, title="World & Package Sets",
            footer_keys=[("Tab", "Pane"), ("Esc", "Back")],
            help_text=(
                "Browse Portage's package sets. The left pane lists them; the\n"
                "right pane shows the members of the focused set.\n\n"
                "The World set is the packages you installed explicitly — the only\n"
                "editable set here. Deselecting a package removes it from @world\n"
                "but does NOT unmerge it; the next Clean Up (depclean) may then\n"
                "reclaim it once nothing else needs it. @system, @profile and any\n"
                "custom sets (/etc/portage/sets) are read-only.\n\n"
                "↑/↓    move within a pane        Tab   next pane\n"
                "Enter/→   (on a set) view its members    ←  back to the set list\n"
                "Space  mark / unmark a World-set package\n"
                "a / n  mark all / none           F10   deselect the marked ones\n"
                "Esc    back"
            ),
        )
        urwid.connect_signal(self._set_walker, "modified", self._on_set_change)
        app.run_async(self._load())

    # -- panes --------------------------------------------------------------

    def _current_pane(self) -> str:
        if self._pile.focus_position == 2:                    # action row
            return ("cancel" if self._actions.focus_position
                    == self._actions.button_position(0) else "deselect")
        return "sets" if self._columns.focus_position == 0 else "members"

    def _focus_pane(self, name: str) -> None:
        if name == "sets":
            self._pile.focus_position = 0
            self._columns.focus_position = 0
        elif name == "members":
            self._pile.focus_position = 0
            self._columns.focus_position = 1
        elif name == "cancel":
            self._pile.focus_position = 2
            self._actions.focus_position = self._actions.button_position(0)
        else:                                                 # deselect
            self._pile.focus_position = 2
            self._actions.focus_position = self._actions.button_position(1)

    def _cycle_pane(self, delta: int = 1) -> None:
        i = self._PANES.index(self._current_pane())
        self._focus_pane(self._PANES[(i + delta) % len(self._PANES)])

    def _footer_context(self):
        pane = self._current_pane()
        tail = [("Tab", "Pane"), ("Esc", "Back")]
        if pane in ("cancel", "deselect"):
            return [("Enter", "Activate"), *tail]
        custom = self._focused_is_custom()
        if pane == "sets":
            keys = [("↑/↓", "Set"), ("Enter/→", "Members"), ("c", "New set")]
            if custom:
                keys += [("a", "Add"), ("d", "Delete")]
            return [*keys, *tail]
        if self._is_world():                                  # members, World set
            return [("Space", "Mark"), ("a", "All"), ("n", "None"),
                    ("F10", "Deselect"), ("←", "Sets"), *tail]
        if custom:                                            # members, custom set
            return [("a", "Add"), ("x", "Remove"), ("c", "New set"),
                    ("←", "Sets"), *tail]
        return [("c", "New set"), ("←", "Sets"), *tail]       # built-in, read-only

    # -- loading / rendering ------------------------------------------------

    async def _load(self) -> None:
        pkgs = await self.app.run_blocking(reader.list_installed)
        self._world_pkgs = sorted((p for p in pkgs if p.world_member),
                                  key=lambda p: p.cp)
        self._sets = await self.app.run_blocking(sets.list_sets)
        self._marked &= {p.cp for p in self._world_pkgs}      # drop stale marks
        self._populate_sidebar()

    def _populate_sidebar(self) -> None:
        entries = [("World set", len(self._world_pkgs))]
        entries += [(s.name, len(s.atoms)) for s in self._sets]
        prev = self._set_walker.focus or 0
        self._set_walker[:] = [
            row(f" {label:<20}{count:>4}") for label, count in entries]
        self._set_walker.set_focus(min(prev, len(entries) - 1))
        self._rebuild_members(reset_focus=True)

    def _is_world(self) -> bool:
        return self._set_walker.focus == 0

    def _focused_set(self) -> PackageSet | None:
        i = self._set_walker.focus
        return self._sets[i - 1] if i >= 1 and i - 1 < len(self._sets) else None

    def _focused_is_custom(self) -> bool:
        s = self._focused_set()
        return s is not None and s.kind == "custom"

    def _on_set_change(self) -> None:
        self._rebuild_members(reset_focus=True)

    def _rebuild_members(self, *, reset_focus: bool = False) -> None:
        prev = self._walker.focus or 0
        if self._is_world():
            self._member_header.base_widget.set_text(
                _fmt("", "Category", "Package", "Version"))
            if not self._world_pkgs:
                self._walker[:] = [urwid.Text(("dim", " The World set is empty."))]
            else:
                self._walker[:] = [
                    row(_fmt("✓" if p.cp in self._marked else "",
                             p.category, p.name, p.version),
                        None if p.cp in self._marked else "dim")
                    for p in self._world_pkgs]
        else:
            s = self._focused_set()
            self._member_header.base_widget.set_text(f"{s.name} — {s.description}")
            self._walker[:] = ([row(f"  {a}", "dim") for a in s.atoms]
                               if s.atoms else [urwid.Text(("dim", " (empty set)"))])
        if len(self._walker):
            self._walker.set_focus(0 if reset_focus
                                   else min(prev, len(self._walker) - 1))
        self._refresh_count()
        self.app.refresh()

    def _refresh_count(self) -> None:
        if self._is_world():
            total, marked = len(self._world_pkgs), len(self._marked)
            if not total:
                self._count.set_text(("dim", " World set is empty"))
            elif not marked:
                self._count.set_text(
                    ("dim", f" World set — {total} explicitly-installed packages"))
            else:
                self._count.set_text([("ok", f" Deselect {marked} of {total}"),
                                      ("dim", "   ·   F10 Deselect")])
        else:
            s = self._focused_set()
            if s.kind == "custom":
                self._count.set_text([
                    ("dim", f" {s.name} — {len(s.atoms)} atoms"),
                    ("dim", "   ·   a Add · x Remove · d Delete")])
            else:
                self._count.set_text(
                    ("dim", f" {s.name} — {len(s.atoms)} atoms · read-only"))

    # -- keys ---------------------------------------------------------------

    def _current_world_pkg(self) -> Package | None:
        i = self._walker.focus
        if self._is_world() and self._world_pkgs and 0 <= i < len(self._world_pkgs):
            return self._world_pkgs[i]
        return None

    def handle_key(self, key):
        if key == "tab":
            self._cycle_pane(1)
            return None
        if key == "shift tab":
            self._cycle_pane(-1)
            return None
        if self._pile.focus_position == 2:                    # on the action row
            if key in ("enter", " "):
                self._actions.activate_focused()
                return None
            if key != "esc":
                return key
        if key == "esc":
            self.app.pop()
            return None
        if key == "r":
            self.app.run_async(self._load())
            return None
        if key == "f10":
            self._deselect()
            return None
        if key == "c":                                        # create a custom set
            self._new_set()
            return None
        set_ = self._focused_set()
        if set_ is not None and set_.kind == "custom":        # editable set
            if key == "a":
                self._add_atom(set_)
                return None
            if key == "d":
                self._delete_set(set_)
                return None
            if key == "x" and self._current_pane() == "members":
                self._remove_atom(set_)
                return None
        if self._current_pane() == "sets" and key == "enter":
            self._focus_pane("members")
            return None
        if self._current_pane() == "members" and self._is_world():
            if key == " ":
                self._toggle()
                return None
            if key == "a":
                self._marked = {p.cp for p in self._world_pkgs}
                self._rebuild_members()
                return None
            if key == "n":
                self._marked.clear()
                self._rebuild_members()
                return None
        return key

    def _toggle(self) -> None:
        pkg = self._current_world_pkg()
        if pkg is None:
            return
        self._marked.discard(pkg.cp) if pkg.cp in self._marked \
            else self._marked.add(pkg.cp)
        self._rebuild_members()

    # -- deselect -----------------------------------------------------------

    def _deselect(self) -> None:
        if not self._is_world():
            self.app.notify("Deselect applies to the World set.", error=True)
            return
        atoms = [p.cp for p in self._world_pkgs if p.cp in self._marked]
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
        atoms = [p.cp for p in self._world_pkgs if p.cp in self._marked]
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

    # -- custom sets --------------------------------------------------------

    def _new_set(self) -> None:
        edit = urwid.Edit("Set name: @")

        def create():
            name = edit.edit_text.strip()
            self.app.pop()                                    # the modal
            if not sets.valid_set_name(name):
                self.app.notify("Invalid set name.", error=True)
                return
            if any(s.name == f"@{name}" for s in self._sets):
                self.app.notify(f"@{name} already exists.", error=True)
                return
            self._write_set(name, [], f"Created @{name}")

        modal = Modal(self.app, "New package set", [edit],
                      [("Create", create), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 60))

    def _add_atom(self, set_: PackageSet) -> None:
        name = set_.name[1:]
        atoms = list(set_.atoms)
        edit = urwid.Edit("Atom: ")

        def add():
            atom = edit.edit_text.strip()
            self.app.pop()                                    # the modal
            if not sets.valid_entry(atom):
                self.app.notify("Invalid atom.", error=True)
                return
            if atom in atoms:
                self.app.notify(f"{atom} is already in {set_.name}.")
                return
            self._write_set(name, [*atoms, atom], f"Added {atom} to {set_.name}")

        modal = Modal(self.app, f"Add to {set_.name}", [edit],
                      [("Add", add), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 60))

    def _remove_atom(self, set_: PackageSet) -> None:
        i = self._walker.focus
        if not (set_.atoms and 0 <= i < len(set_.atoms)):
            return
        atom = set_.atoms[i]
        remaining = [a for a in set_.atoms if a != atom]
        self._write_set(set_.name[1:], remaining, f"Removed {atom} from {set_.name}")

    def _delete_set(self, set_: PackageSet) -> None:
        def do():
            self.app.pop()                                    # the modal
            self._delete_set_file(set_.name[1:], f"Deleted {set_.name}")

        modal = Modal(
            self.app, f"Delete {set_.name}?",
            [urwid.Text(("hint", "Removes the set file. Installed packages are "
                         "untouched."))],
            [("Delete", do), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 60))

    def _write_set(self, name: str, atoms: list[str], ok_msg: str) -> None:
        write = ConfigWrite(sets.set_path(name), sets.render_set(atoms))
        self.app.run_async(self._apply_write(write, ok_msg))

    def _delete_set_file(self, name: str, ok_msg: str) -> None:
        write = ConfigWrite(sets.set_path(name), "")          # empty text = delete
        self.app.run_async(self._apply_write(write, ok_msg))

    async def _apply_write(self, write: ConfigWrite, ok_msg: str) -> None:
        backend = PortageBackend()
        try:
            await backend.connect()
            ok = await backend.write_config([write])
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            with contextlib.suppress(Exception):
                await backend.close()
            return
        await backend.close()
        self.app.notify(ok_msg if ok else "Write failed.", error=not ok)
        await self._load()
