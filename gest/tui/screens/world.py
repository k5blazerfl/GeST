"""World & Package Sets (urwid): browse Portage sets; manage @world and custom sets.

A two-pane browser. Left: the package sets — the **World set** (packages you
installed explicitly), Portage's built-in @system / @profile, then custom sets
under /etc/portage/sets. Right: the members of the focused set.

Edits are **transactional**: marking @world packages to deselect, and adding /
removing atoms or creating / deleting custom sets, all *stage* the change (shown
inline — ✓ deselect, + add, - remove, and a modified marker in the sidebar).
Nothing is written until **F10 (Apply)**, which commits everything at once:
custom-set edits through the Portage backend and deselects via
``emerge --deselect``. @system / @profile are read-only. Deselecting unmerges
nothing — it only drops the explicit-install record so a later Clean Up may
reclaim the package.
"""

from __future__ import annotations

import contextlib

import urwid

from gest.core.portage.backend_client import PortageBackend
from gest.core.portage.write import ConfigWrite
from gest.core.software import reader, sets
from gest.core.software.backend_client import SoftwareBackend
from gest.core.software.model import Package
from gest.tui.runtime import App, Modal, NavPile, Screen, boxed, focusable_actions
from gest.tui.screens.runscreen import clip, row

_MARK_W = 2
_CAT_W = 16
_PKG_W = 26
_VER_W = 16


def _fmt(mark: str, cat: str, pkg: str, ver: str) -> str:
    return (f"{mark:<{_MARK_W}}{clip(cat, _CAT_W):<{_CAT_W}}"
            f"{clip(pkg, _PKG_W):<{_PKG_W}}{clip(ver, _VER_W):<{_VER_W}}")


class WorldScreen(Screen):
    # Tab stops, in order.
    _PANES = ("sets", "members", "cancel", "apply")

    def __init__(self, app: App) -> None:
        self._world_pkgs: list[Package] = []
        self._marked: set[str] = set()             # @world cp's to deselect
        self._sets: list = []                      # on-disk sets (built-ins + custom)
        self._disk: dict[str, list[str]] = {}      # on-disk custom sets (cached on load)
        self._edits: dict[str, list[str] | None] = {}   # name → atoms, or None = delete
        self._sidebar: list[tuple[str, object]] = []    # (kind, payload) per row
        self._member_atoms: list[str] = []         # custom member index → atom
        self._focus_name: str | None = None        # set to focus after a rebuild
        self._last_set_focus = 0                   # guard: rebuild only on real moves

        self._set_walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._set_list = urwid.ListBox(self._set_walker)
        left = boxed(self._set_list, title="Package sets")

        self._member_header = urwid.AttrMap(urwid.Text("", wrap="clip"), "pane_title")
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        right = boxed(
            urwid.Pile([("pack", self._member_header),
                        ("pack", urwid.Divider("─")),
                        ("weight", 1, self._list)]),
            title="Members")

        self._columns = urwid.Columns([(30, left), right], dividechars=1)
        self._count = urwid.Text("")
        self._actions = focusable_actions([
            ("Cancel", app.pop), ("Apply", self._apply)])
        self._pile = NavPile([
            ("weight", 1, self._columns),
            ("pack", self._count),
            ("pack", self._actions),
        ])
        super().__init__(
            app, self._pile, title="World & Package Sets",
            footer_keys=[("Tab", "Pane"), ("Esc", "Back")],
            help_text=(
                "Browse Portage's package sets and manage @world and custom sets.\n"
                "Left pane: the sets; right pane: the focused set's members.\n\n"
                "Edits are staged and applied together with F10 (Apply):\n"
                "  World set   Space marks a package to deselect (✓)\n"
                "  Custom set  a add an atom · x remove/restore · d delete · c new\n"
                "Inline markers show staged changes: ✓ deselect · + add · - remove.\n"
                "Deselecting unmerges nothing — it drops the @world record so a\n"
                "later Clean Up may reclaim the package. @system / @profile are\n"
                "read-only.\n\n"
                "Tab moves between panes · F10 applies · Esc discards and goes back."
            ),
        )
        # Rebuild the member pane whenever the focused set changes — however the
        # focus moved (arrow key or mouse), matching the app-wide idiom.
        urwid.connect_signal(self._set_walker, "modified", self._on_set_change)
        app.run_async(self._load())

    # -- panes --------------------------------------------------------------

    def _current_pane(self) -> str:
        if self._pile.focus_position == 2:
            return ("cancel" if self._actions.focus_position
                    == self._actions.button_position(0) else "apply")
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
        else:                                                 # apply
            self._pile.focus_position = 2
            self._actions.focus_position = self._actions.button_position(1)

    def _cycle_pane(self, delta: int = 1) -> None:
        i = self._PANES.index(self._current_pane())
        self._focus_pane(self._PANES[(i + delta) % len(self._PANES)])

    def _footer_context(self):
        pane = self._current_pane()
        tail = [("Tab", "Pane"), ("Esc", "Back")]
        apply = [("F10", "Apply")] if self._has_pending() else []
        if pane in ("cancel", "apply"):
            return [("Enter", "Activate"), *tail]
        custom = self._focused_custom() is not None
        if pane == "sets":
            keys = [("↑/↓", "Set"), ("Enter/→", "Members"), ("c", "New set")]
            if custom:
                keys += [("a", "Add"), ("d", "Delete")]
            return [*keys, *apply, *tail]
        if self._is_world():                                  # members, World set
            return [("Space", "Mark"), ("a", "All"), ("n", "None"),
                    *apply, ("←", "Sets"), *tail]
        if custom:                                            # members, custom set
            return [("a", "Add"), ("x", "Remove"), ("c", "New set"),
                    *apply, ("←", "Sets"), *tail]
        return [("c", "New set"), ("←", "Sets"), *tail]       # built-in, read-only

    # -- loading / sidebar --------------------------------------------------

    async def _load(self) -> None:
        pkgs = await self.app.run_blocking(reader.list_installed)
        self._world_pkgs = sorted((p for p in pkgs if p.world_member),
                                  key=lambda p: p.cp)
        self._sets = await self.app.run_blocking(sets.list_sets)
        # The on-disk custom sets are invariant between loads, so snapshot them
        # once rather than rescanning self._sets in every predicate.
        self._disk = {s.name[1:]: list(s.atoms)
                      for s in self._sets if s.kind == "custom"}
        self._marked &= {p.cp for p in self._world_pkgs}      # drop stale marks
        self._populate_sidebar()

    def _custom_names(self) -> list[str]:
        return sorted(set(self._disk) | set(self._edits))

    def _base_atoms(self, name: str) -> list[str]:
        return self._disk.get(name, [])

    def _working_atoms(self, name: str) -> list[str] | None:
        return self._edits[name] if name in self._edits else self._base_atoms(name)

    def _deleted(self, name: str) -> bool:
        return name in self._edits and self._edits[name] is None

    def _is_new(self, name: str) -> bool:
        return name not in self._disk and self._edits.get(name) is not None

    def _modified(self, name: str) -> bool:
        # In _edits and differing from disk — covers add/remove (list != disk),
        # delete (None != disk atoms), and a staged new set (value != absent).
        return name in self._edits and self._edits[name] != self._disk.get(name)

    def _has_pending(self) -> bool:
        return bool(self._marked) or bool(self._edits)

    def _populate_sidebar(self) -> None:
        self._sidebar = [("world", None)]
        self._sidebar += [("builtin", s) for s in self._sets if s.kind == "builtin"]
        self._sidebar += [("custom", n) for n in self._custom_names()]
        prev = self._set_walker.focus or 0
        self._set_walker[:] = [self._sidebar_row(e) for e in self._sidebar]
        idx = (self._sidebar_index(self._focus_name)
               if self._focus_name else min(prev, len(self._sidebar) - 1))
        self._focus_name = None
        idx = max(0, min(idx, len(self._sidebar) - 1))
        self._set_walker.set_focus(idx)
        self._last_set_focus = idx
        self._rebuild_members(reset_focus=True)

    def _sidebar_row(self, entry) -> urwid.Widget:
        kind, payload = entry
        if kind == "world":
            return row(f" {'World set':<20}{len(self._world_pkgs):>4}")
        if kind == "builtin":
            return row(f" {payload.name:<20}{len(payload.atoms):>4}")
        name = payload
        marker, attr = self._custom_marker(name)
        working = self._working_atoms(name)
        cnt = "" if working is None else str(len(working))
        return row(f"{marker}@{name:<19}{cnt:>4}", attr)

    def _custom_marker(self, name: str) -> tuple[str, str | None]:
        if self._deleted(name):
            return ("-", "error")
        if self._modified(name):
            return ("*", "ok")
        return (" ", None)

    def _sidebar_index(self, name: str) -> int:
        for i, (kind, payload) in enumerate(self._sidebar):
            if kind == "custom" and payload == name:
                return i
        return 0

    def _update_sidebar_row(self, name: str) -> None:
        # In-place refresh of one custom row (count/marker) without a full
        # repopulate, so member focus is preserved while editing atoms.
        idx = self._sidebar_index(name)
        self._set_walker[idx] = self._sidebar_row(("custom", name))

    # -- focus / members ----------------------------------------------------

    def _on_set_change(self) -> None:
        # Fired on every walker mutation; rebuild the member pane only when the
        # focused set actually changed (so in-place row refreshes during an edit
        # don't stomp member focus).
        i = self._set_walker.focus
        if i == self._last_set_focus:
            return
        self._last_set_focus = i
        self._rebuild_members(reset_focus=True)
        self._refresh_footer()

    def _focused_entry(self):
        i = self._set_walker.focus
        return self._sidebar[i] if 0 <= i < len(self._sidebar) else None

    def _is_world(self) -> bool:
        e = self._focused_entry()
        return e is not None and e[0] == "world"

    def _focused_custom(self) -> str | None:
        e = self._focused_entry()
        return e[1] if e is not None and e[0] == "custom" else None

    def _rebuild_members(self, *, reset_focus: bool = False) -> None:
        prev = self._walker.focus or 0
        self._member_atoms = []
        e = self._focused_entry()
        kind = e[0] if e else None
        if kind == "world":
            self._render_world_members()
        elif kind == "builtin":
            self._render_builtin_members(e[1])
        elif kind == "custom":
            self._render_custom_members(e[1])
        else:
            self._walker[:] = [urwid.Text("")]
        if len(self._walker):
            self._walker.set_focus(0 if reset_focus
                                   else min(prev, len(self._walker) - 1))
        self._refresh_count()
        self.app.refresh()

    def _render_world_members(self) -> None:
        self._member_header.base_widget.set_text(
            _fmt("", "Category", "Package", "Version"))
        if not self._world_pkgs:
            self._walker[:] = [urwid.Text(("dim", " The World set is empty."))]
            return
        self._walker[:] = [
            row(_fmt("✓" if p.cp in self._marked else "",
                     p.category, p.name, p.version),
                None if p.cp in self._marked else "dim")
            for p in self._world_pkgs]

    def _render_builtin_members(self, s) -> None:
        self._member_header.base_widget.set_text(f"{s.name} — {s.description}")
        self._walker[:] = ([row(f"  {a}", "dim") for a in s.atoms]
                           if s.atoms else [urwid.Text(("dim", " (empty set)"))])

    def _render_custom_members(self, name: str) -> None:
        working = self._working_atoms(name)
        if working is None:                                   # staged delete
            self._member_header.base_widget.set_text(f"@{name} — will be deleted")
            self._walker[:] = [
                urwid.Text(("error", " (set will be deleted on Apply)"))]
            return
        header = f"@{name}"
        if self._modified(name):
            header += "   • modified (F10 to apply)"
        self._member_header.base_widget.set_text(header)
        base = self._base_atoms(name)
        rows: list[urwid.Widget] = []
        atoms: list[str] = []
        for a in base:                                        # kept / staged-remove
            rows.append(row(f"  {a}", "dim") if a in working
                        else row(f"- {a}", "error"))
            atoms.append(a)
        for a in working:                                     # staged-add
            if a not in base:
                rows.append(row(f"+ {a}", "ok"))
                atoms.append(a)
        self._walker[:] = rows or [urwid.Text(("dim", " (empty set)"))]
        self._member_atoms = atoms

    def _refresh_count(self) -> None:
        e = self._focused_entry()
        kind = e[0] if e else None
        if kind == "world":
            total, marked = len(self._world_pkgs), len(self._marked)
            if not total:
                parts = [("dim", " World set is empty")]
            elif marked:
                parts = [("ok", f" Deselect {marked} of {total}")]
            else:
                parts = [("dim", f" World set — {total} explicitly-installed")]
        elif kind == "builtin":
            parts = [("dim", f" {e[1].name} — {len(e[1].atoms)} atoms · read-only")]
        elif kind == "custom":
            working = self._working_atoms(e[1])
            parts = ([("error", f" @{e[1]} — will be deleted")] if working is None
                     else [("dim", f" @{e[1]} — {len(working)} atoms")])
        else:
            parts = [("dim", "")]
        summary = self._pending_summary()
        if summary:
            parts.append(("ok", f"   ·   {summary} · F10 Apply"))
        self._count.set_text(parts)

    def _pending_summary(self) -> str:
        bits = []
        if self._marked:
            bits.append(f"deselect {len(self._marked)}")
        n = len(self._edits)
        if n:
            bits.append(f"{n} set change{'s' if n != 1 else ''}")
        return " · ".join(bits)

    # -- keys ---------------------------------------------------------------

    def handle_key(self, key):
        if key == "tab":
            self._cycle_pane(1)
            return None
        if key == "shift tab":
            self._cycle_pane(-1)
            return None
        if self._pile.focus_position == 2:                    # action row
            if key in ("enter", " "):
                self._actions.activate_focused()
                return None
            if key != "esc":
                return key
        if key == "esc":
            self.app.pop()
            return None
        if key == "r":
            self._reload()
            return None
        if key == "f10":
            self._apply()
            return None
        if key == "c":
            self._new_set()
            return None
        name = self._focused_custom()
        if name is not None:
            if key == "a":
                self._add_atom(name)
                return None
            if key == "d":
                self._toggle_delete(name)
                return None
            if key == "x" and self._current_pane() == "members":
                self._toggle_atom(name)
                return None
        if self._current_pane() == "sets" and key == "enter":
            self._focus_pane("members")
            return None
        if self._current_pane() == "members" and self._is_world():
            if key == " ":
                self._toggle_mark()
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

    def _reload(self) -> None:
        self._edits.clear()                                   # discard staged edits
        self.app.run_async(self._load())

    def _toggle_mark(self) -> None:
        i = self._walker.focus
        if not (self._world_pkgs and 0 <= i < len(self._world_pkgs)):
            return
        p = self._world_pkgs[i]
        self._marked.discard(p.cp) if p.cp in self._marked else self._marked.add(p.cp)
        marked = p.cp in self._marked
        self._walker[i] = row(_fmt("✓" if marked else "", p.category, p.name,
                                   p.version), None if marked else "dim")
        self._refresh_count()                                 # patch one row, not all
        self.app.refresh()

    # -- staged custom-set edits --------------------------------------------

    def _stage(self, name: str, atoms: list[str]) -> None:
        if name in self._disk and atoms == self._disk[name]:
            self._edits.pop(name, None)                       # back to unmodified
        else:
            self._edits[name] = atoms
        self._rebuild_members()
        self._update_sidebar_row(name)

    def _new_set(self) -> None:
        edit = urwid.Edit("Set name: @")

        def create():
            name = edit.edit_text.strip()
            self.app.pop()
            if not sets.valid_set_name(name):
                self.app.notify("Invalid set name.", error=True)
                return
            if name in self._disk or self._is_new(name):
                self.app.notify(f"@{name} already exists.", error=True)
                return
            self._edits[name] = []                            # stage an empty new set
            self._focus_name = name
            self._populate_sidebar()
            self.app.notify(f"Staged new set @{name} — F10 to apply")

        modal = Modal(self.app, "New package set", [edit],
                      [("Create", create), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 60))

    def _add_atom(self, name: str) -> None:
        working = self._working_atoms(name)
        if working is None:
            self.app.notify("Set is staged for deletion.", error=True)
            return
        edit = urwid.Edit("Atom: ")

        def add():
            atom = edit.edit_text.strip()
            self.app.pop()
            if not sets.valid_entry(atom):
                self.app.notify("Invalid atom.", error=True)
                return
            if atom in working:
                self.app.notify(f"{atom} is already in @{name}.")
                return
            self._stage(name, [*working, atom])

        modal = Modal(self.app, f"Add to @{name}", [edit],
                      [("Add", add), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 60))

    def _toggle_atom(self, name: str) -> None:
        working = self._working_atoms(name)
        atom = (self._member_atoms[self._walker.focus]
                if 0 <= self._walker.focus < len(self._member_atoms) else None)
        if working is None or atom is None:
            return
        new = ([a for a in working if a != atom] if atom in working
               else [*working, atom])
        self._stage(name, new)

    def _toggle_delete(self, name: str) -> None:
        if self._deleted(name) or self._is_new(name):
            self._edits.pop(name, None)                       # un-delete / cancel new
        else:
            self._edits[name] = None                          # stage delete
        self._populate_sidebar()

    # -- apply (commit everything staged) -----------------------------------

    def _apply(self) -> None:
        if not self._has_pending():
            self.app.notify("Nothing to apply.")
            return
        lines = []
        if self._marked:
            lines.append(f"Deselect {len(self._marked)} package(s) from @world")
        for name in sorted(self._edits):
            v = self._edits[name]
            if v is None:
                lines.append(f"Delete set @{name}")
            elif name not in self._disk:
                lines.append(f"Create set @{name} ({len(v)} atom(s))")
            else:
                lines.append(f"Update set @{name} ({len(v)} atom(s))")
        body = [urwid.Text(("hint", f" • {line}")) for line in lines]
        modal = Modal(self.app, "Apply staged changes?", body,
                      [("Apply", self._run_apply), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 64))

    def _run_apply(self) -> None:
        self.app.pop()                                        # the confirm modal
        self.app.run_async(self._commit())

    async def _commit(self) -> None:
        ok = True
        msgs: list[str] = []
        if self._edits:
            writes = [ConfigWrite(sets.set_path(n),
                                  "" if v is None else sets.render_set(v))
                      for n, v in self._edits.items()]
            okw = await self._write(writes)
            ok = ok and okw
            msgs.append(f"{len(writes)} set change(s) {'ok' if okw else 'failed'}")
        if self._marked:
            okd = await self._deselect(sorted(self._marked))
            ok = ok and okd
            msgs.append(f"deselect {'ok' if okd else 'failed'}")
        self.app.notify(" · ".join(msgs) or "done", error=not ok)
        if ok:
            self._edits.clear()
            self._marked.clear()
        await self._load()

    async def _run_backend(self, backend, op):
        """connect → op(backend) → close, notifying on failure. Returns op's
        result, or None if it raised."""
        try:
            await backend.connect()
            return await op(backend)
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            return None
        finally:
            with contextlib.suppress(Exception):
                await backend.close()

    async def _write(self, writes: list[ConfigWrite]) -> bool:
        ok = await self._run_backend(PortageBackend(),
                                     lambda b: b.write_config(writes))
        return bool(ok)

    async def _deselect(self, atoms: list[str]) -> bool:
        result = await self._run_backend(SoftwareBackend(),
                                         lambda b: b.deselect(atoms))
        return bool(result and result[0])
