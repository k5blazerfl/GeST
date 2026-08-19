"""Unavailable Packages (urwid): repo-orphans + Deselect / Unmerge.

Lists installed packages with no ebuild in any configured repo — an overlay
renamed or dropped them, or was removed. Distinct from Clean Up (depclean): those
are packages nothing needs; these are still wanted but unmaintainable, and
depclean won't surface them (a @world member is protected, one with dependents is
kept). The table shows Category · Package · Version · Flags · Size, with a Details
pane explaining why each is unavailable and what still depends on it.

Two actions on the marked packages: Deselect drops @world members from the set
(``emerge --deselect``, unmerges nothing); Unmerge forcibly removes them
(``emerge --unmerge`` via :class:`ApplyScreen`), always behind a confirmation
that spells out reverse dependencies — it has no safety net.
"""

from __future__ import annotations

import contextlib

import urwid

from gest.core.software.backend_client import SoftwareBackend
from gest.core.software.cleanup import human_size
from gest.core.software.orphans import OrphanReport, RepoOrphan, scan_orphans
from gest.tui.runtime import App, Modal, NavPile, Screen, boxed, focusable_actions
from gest.tui.screens.apply import ApplyScreen, unmerge_plan
from gest.tui.screens.runscreen import clip, row

_MARK_W = 2   # ✓ = marked for action
_CAT_W = 16
_PKG_W = 20
_VER_W = 15
_TAG_W = 16
_SIZE_W = 11


def _fmt(mark: str, cat: str, pkg: str, ver: str, tags: str, size: str) -> str:
    return (f"{mark:<{_MARK_W}}{clip(cat, _CAT_W):<{_CAT_W}}{clip(pkg, _PKG_W):<{_PKG_W}}"
            f"{clip(ver, _VER_W):<{_VER_W}}{clip(tags, _TAG_W):<{_TAG_W}}"
            f"{size:>{_SIZE_W}}")


def _tags(o: RepoOrphan) -> str:
    parts = []
    if o.world_member:
        parts.append("@world")
    if o.required_by:
        parts.append(f"needs:{len(o.required_by)}")
    return " ".join(parts)


def _orphan_line(o: RepoOrphan, marked: bool) -> str:
    return _fmt("✓" if marked else "", o.category, o.package, o.version,
                _tags(o), human_size(o.size))


class OrphansScreen(Screen):
    def __init__(self, app: App) -> None:
        self._report = OrphanReport()
        self._marked: set[str] = set()   # cp of packages marked for action
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" scanning …")])
        self._list = urwid.ListBox(self._walker)

        header = urwid.AttrMap(
            urwid.Text(_fmt("", "Category", "Package", "Version", "Flags", "Size"),
                       wrap="clip"),
            "pane_title")
        table = boxed(
            urwid.Pile([
                ("pack", header),
                ("pack", urwid.Divider("─")),
                ("weight", 1, self._list),
            ]),
            title="Unavailable packages")

        self._details = urwid.Pile([urwid.Text("")])
        details_box = boxed(self._details, title="Details")
        self._count = urwid.Text("")

        self._actions = focusable_actions([
            ("Cancel", app.pop),
            ("Deselect", self._deselect_marked),
            ("Unmerge", self._unmerge_marked),
        ])
        body = NavPile([
            ("weight", 1, table),
            ("pack", details_box),
            ("pack", self._count),
            ("pack", self._actions),
        ])
        super().__init__(
            app, body, title="Unavailable Packages",
            footer_keys=[
                ("Space", "Mark"), ("a", "All"), ("n", "None"),
                ("r", "Rescan"), ("Esc", "Back"),
            ],
            help_text=(
                "Unavailable packages — installed, but no ebuild for them exists in\n"
                "any configured repo (an overlay renamed or dropped them, or was\n"
                "removed). They still run but can't be updated or reinstalled, and\n"
                "Clean Up (depclean) won't remove them while they're in @world or\n"
                "something needs them.\n\n"
                "Columns:  Category · Package · Version · Flags · Size.\n"
                "Flags:  @world (explicitly installed)   needs:N (reverse deps).\n\n"
                "Space    mark / unmark the highlighted package\n"
                "a  mark all      n  clear marks      r  rescan\n"
                "Deselect  drop marked @world members (emerge --deselect)\n"
                "Unmerge   force-remove marked packages (emerge --unmerge)\n"
                "Esc      back"
            ),
        )
        self.configure_pane_cycle(body, [0], action_row=self._actions)
        app.run_async(self._load())

    # -- data ---------------------------------------------------------------

    async def _load(self) -> None:
        self._report = await self.app.run_blocking(scan_orphans)
        self._marked &= {o.cp for o in self._report.orphans}   # drop stale marks
        self._rebuild()

    def _orphans(self) -> list[RepoOrphan]:
        return self._report.orphans

    # -- rendering ----------------------------------------------------------

    def _rebuild(self) -> None:
        focus = self._walker.focus or 0
        if not self._orphans():
            self._walker[:] = [urwid.Text(
                ("ok", " No unavailable packages — every installed package still "
                       "has an ebuild in a configured repo."))]
        else:
            self._walker[:] = [
                row(_orphan_line(o, o.cp in self._marked),
                    None if o.cp in self._marked else "dim")
                for o in self._orphans()]
            self._walker.set_focus(min(focus, len(self._orphans()) - 1))
        self._render_details()
        self._refresh_count()
        self.app.refresh()

    def _render_details(self) -> None:
        cur = self._current()
        if cur is None:
            rows: list[urwid.Widget] = [
                urwid.Text(("hint", " Select a package to see why it's unavailable."))]
        else:
            rows = [urwid.Text([("field", " "),
                                f"{cur.cpv} — no ebuild in any configured repo."])]
            if cur.world_member:
                rows.append(urwid.Text(
                    [("field", " @world "),
                     "explicitly installed; deselect before depclean can reclaim it."]))
            if cur.required_by:
                shown = ", ".join(cur.required_by[:6])
                more = " …" if len(cur.required_by) > 6 else ""
                rows.append(urwid.Text([("error", " needed by "), shown + more,
                                        " — unmerging may break these."]))
            else:
                rows.append(urwid.Text(
                    [("ok", " safe "),
                     "nothing installed depends on it — unmerging strands nothing."]))
        self._details.contents = [(w, self._details.options("pack")) for w in rows]

    def _refresh_count(self) -> None:
        orphans = self._orphans()
        if not orphans:
            self._count.set_text(("dim", " Nothing to do"))
            return
        marked = self._marked_orphans()
        if not marked:
            self._count.set_text(
                ("dim", f" {len(orphans)} unavailable · Space to mark"))
            return
        size = human_size(sum(o.size for o in marked))
        self._count.set_text([
            ("ok", f" {len(marked)} marked"),
            ("dim", f"   ·   {size} installed   ·   Deselect or Unmerge"),
        ])

    # -- keys ---------------------------------------------------------------

    def _current(self) -> RepoOrphan | None:
        orphans = self._orphans()
        if orphans and 0 <= self._walker.focus < len(orphans):
            return orphans[self._walker.focus]
        return None

    def _marked_orphans(self) -> list[RepoOrphan]:
        return [o for o in self._orphans() if o.cp in self._marked]

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
        elif key in ("r", "R"):
            self.app.run_async(self._load())
        elif key == " ":
            self._toggle()
        elif key == "a":
            self._marked = {o.cp for o in self._orphans()}
            self._rebuild()
        elif key == "n":
            self._marked.clear()
            self._rebuild()
        else:
            return key
        return None

    def _toggle(self) -> None:
        cur = self._current()
        if cur is None:
            return
        self._marked.discard(cur.cp) if cur.cp in self._marked \
            else self._marked.add(cur.cp)
        self._rebuild()

    # -- actions ------------------------------------------------------------

    def _deselect_marked(self) -> None:
        members = [o for o in self._marked_orphans() if o.world_member]
        if not members:
            self.app.notify("Mark one or more @world members to deselect.", error=True)
            return
        self.app.run_async(self._do_deselect([o.cp for o in members]))

    async def _do_deselect(self, atoms: list[str]) -> None:
        result = await self._run_backend(SoftwareBackend(),
                                         lambda b: b.deselect(atoms))
        ok = bool(result and result[0])
        self.app.notify(
            f"Deselected {len(atoms)} from @world." if ok else "Deselect failed.",
            error=not ok)
        await self._load()

    def _unmerge_marked(self) -> None:
        marked = self._marked_orphans()
        if not marked:
            self.app.notify("Mark one or more packages to unmerge.", error=True)
            return
        depended = [o for o in marked if o.required_by]
        body: list[urwid.Widget] = [
            urwid.Text(("hint",
                        f" Permanently remove {len(marked)} package(s) with "
                        "emerge --unmerge:"))]
        body += [urwid.Text(("dim", f"   • {o.cpv}")) for o in marked]
        if depended:
            body.append(urwid.Divider())
            body.append(urwid.Text(
                ("error", " ⚠ Still required by other installed packages — "
                          "removing may break them:")))
            for o in depended:
                shown = ", ".join(o.required_by[:5])
                more = " …" if len(o.required_by) > 5 else ""
                body.append(urwid.Text(("error", f"   • {o.cpv} ← {shown}{more}")))
        body.append(urwid.Divider())
        body.append(urwid.Text(
            ("hint", " No dependency safety check; this cannot be undone.")))
        atoms = [o.cp for o in marked]
        modal = Modal(self.app, "Unmerge unavailable packages?", body,
                      [("Unmerge", lambda: self._run_unmerge(atoms)),
                       ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 68), height=("relative", 52))

    def _run_unmerge(self, atoms: list[str]) -> None:
        self.app.pop()                                     # the confirm modal
        reload_after = lambda: self.app.run_async(self._load())  # noqa: E731
        self.app.push(ApplyScreen(self.app, [unmerge_plan(atoms)],
                                  verb="Unmerge", on_done=reload_after))

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
