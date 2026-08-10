"""Software repositories (urwid): stage enable/add/disable/remove/refresh, then Accept.

A YaST-style layout consistent with the other transactional modules (Software,
Users): a columnar table over a Properties panel, a pending-count line, and a
[Cancel] [Accept] action bar. Changes are *staged* — shown as a mark glyph in the
row, not applied — until F10 Accept runs `eselect repository` (via the polkit-gated
ReposBackend) and writes the refresh-state file (via the Portage backend). F9
discards. Staged marks reuse the shared vocabulary: + add/enable · ~ disable ·
- remove.
"""

from __future__ import annotations

import urwid

from gest.core.portage.backend_client import PortageBackend
from gest.core.repos import pending, reader, writer
from gest.core.repos.backend_client import ReposBackend
from gest.core.repos.reader import Repo
from gest.tui.runtime import App, Modal, Screen, action_bar

# Table column widths (characters). Name leads (after the mark glyph); Sync URI
# takes the remaining width and is clipped. The Properties panel shows the full
# URI and the repo's priority.
_MARK_W = 2   # ★ main marker or a staged mark glyph (mutually exclusive)
_NAME_W = 24
_AUTO_W = 9   # "AutoSync"
_REFRESH_W = 8  # "Refresh"
_TYPE_W = 8

_TRUTHY = {"yes", "true", "1", "on"}

# Staged-change glyphs — the shared vocabulary (cf. Users: + add · ~ edit · - del).
_STATE_GLYPH = {pending.ENABLE: "+", pending.ADD: "+",
                pending.DISABLE: "~", pending.REMOVE: "-"}


def _fmt(mark: str, name: str, auto: str, refresh: str,
         stype: str, uri: str) -> str:
    if len(name) > _NAME_W - 1:
        name = name[: _NAME_W - 2] + "…"
    return (f"{mark:<{_MARK_W}}{name:<{_NAME_W}}{auto:<{_AUTO_W}}"
            f"{refresh:<{_REFRESH_W}}{stype:<{_TYPE_W}}{uri}")


def _repo_line(r: Repo, mark: str, refresh_cell: str) -> str:
    auto = "x" if r.auto_sync.strip().lower() in _TRUTHY else ""
    lead = mark or ("★" if r.main else "")
    return _fmt(lead, r.name, auto, refresh_cell,
                r.sync_type or "—", r.sync_uri or "—")


def _new_line(name: str, kind: str, spec: pending.AddSpec | None) -> str:
    stype = spec.sync_type if spec else "—"
    uri = spec.uri if spec else "(from eselect repository list)"
    return _fmt(_STATE_GLYPH[kind], name, "", "", stype or "—", uri)


def _row(text: str) -> urwid.Widget:
    icon = urwid.SelectableIcon(text, 0)
    icon.set_wrap_mode("clip")   # keep rows to one line so columns stay aligned
    return urwid.AttrMap(icon, None, focus_map="focus")


class ReposScreen(Screen):
    def __init__(self, app: App) -> None:
        self._repos: list[Repo] = []
        self._pending = pending.Pending()
        # Each walker row maps to an entry: ("repo", Repo) or ("new", name).
        self._entries: list[tuple | None] = []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)

        header = urwid.AttrMap(
            urwid.Text(_fmt("", "Name", "AutoSync", "Refresh", "Type", "Sync URI"),
                       wrap="clip"),
            "pane_title")
        table = urwid.LineBox(
            urwid.Pile([
                ("pack", header),
                ("pack", urwid.Divider("─")),
                ("weight", 1, self._list),
            ]),
            title="Configured software repositories")

        self._props = urwid.Pile([urwid.Text("")])
        props_box = urwid.LineBox(self._props, title="Properties")
        self._count = urwid.Text("")

        body = urwid.Pile([
            ("weight", 1, table),
            ("pack", props_box),
            ("pack", self._count),
            ("pack", action_bar(["Cancel", "Accept"])),
        ])
        urwid.connect_signal(self._walker, "modified", self._on_focus)

        super().__init__(
            app, body,
            title="Repositories",
            footer_keys=[
                ("a", "Enable"), ("A", "Add"), ("d", "Disable"), ("x", "Remove"),
                ("t", "Refresh"), ("F10", "Accept"), ("F9", "Cancel"),
                ("r", "Reload"), ("Esc", "Back"),
            ],
            help_text=(
                "Software repositories configured in /etc/portage/repos.conf.\n\n"
                "Editing is transactional: changes are STAGED as a mark, not applied\n"
                "immediately —\n"
                "  +  enable / add    ~  disable    -  remove\n"
                "shown in the leftmost column (a staged refresh shows + / - in the\n"
                "Refresh column). The count line and [Accept] button sit below the\n"
                "list. F10 (Accept) applies every staged change; F9 (Cancel)\n"
                "discards them; a key pressed twice on a row clears its mark.\n\n"
                "The main (default) repository is marked ★ and is protected — it\n"
                "can't be disabled, removed, or refreshed-on-open.\n\n"
                "Columns:  Name · AutoSync (in emerge --sync) · Refresh (sync on\n"
                "open) · Type · Sync URI. Refresh: when on (x), GeST syncs that repo\n"
                "each time Software Management opens; the ★ main tree is excluded —\n"
                "sync it with the Sync Portage Tree tool.\n\n"
                "a  stage enabling a known repository (from the eselect list)\n"
                "A  stage adding a custom repository (name / sync type / URI)\n"
                "d  stage disabling      x  stage removing (deletes files on Accept;\n"
                "on a staged new repo, x cancels it)      t  toggle refresh-on-open\n"
                "F10 Accept    F9 Cancel    r  reload"
            ),
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        self._repos = await self.app.run_blocking(reader.enabled_repos)
        self._rebuild()

    # -- rendering ----------------------------------------------------------

    def _rebuild(self) -> None:
        """Rebuild the row list from repos + pending, preserving focus."""
        focus = self._walker.focus or 0
        rows: list[urwid.Widget] = []
        entries: list[tuple | None] = []
        for r in self._repos:
            rows.append(_row(_repo_line(r, self._mark_for(r), self._refresh_cell(r))))
            entries.append(("repo", r))
        for name, spec in sorted(self._pending.adds.items()):
            rows.append(_row(_new_line(name, pending.ADD, spec)))
            entries.append(("new", name))
        for name, op in self._pending.state.items():
            if op == pending.ENABLE:
                rows.append(_row(_new_line(name, pending.ENABLE, None)))
                entries.append(("new", name))
        if not rows:
            rows = [urwid.Text(" (no repositories configured)")]
            entries = [None]
        self._entries = entries
        self._walker[:] = rows
        self._walker.set_focus(min(focus, len(rows) - 1))
        self._render_props()
        self._refresh_count()
        self.app.refresh()

    def _mark_for(self, r: Repo) -> str:
        """Leading mark glyph for an existing repo (disable/remove), else ''."""
        op = self._pending.state_of(r.name)
        return _STATE_GLYPH[op] if op in (pending.DISABLE, pending.REMOVE) else ""

    def _refresh_cell(self, r: Repo) -> str:
        if r.main:
            return "—"
        staged = self._pending.refresh_of(r.name)
        if staged is not None:
            return "+" if staged else "-"
        return "x" if r.refresh else ""

    def _refresh_count(self) -> None:
        if self._pending.is_empty:
            self._count.set_text(("dim", " No pending changes"))
        else:
            n = self._pending.count()
            self._count.set_text([
                ("ok", f" {n} pending change{'s' if n != 1 else ''}"),
                ("dim", "   ·   F10 Accept · F9 Cancel"),
            ])

    # -- properties panel ---------------------------------------------------

    def _on_focus(self) -> None:
        self._render_props()

    def _render_props(self) -> None:
        entry = self._current_entry()
        if entry is not None and entry[0] == "new":
            rows: list[urwid.Widget] = [
                urwid.Text([("field", " Staged    "),
                            f"{entry[1]}  (pending new repository — not yet applied)"])]
        else:
            rows = self._prop_rows(self._current())
        self._props.contents = [(w, self._props.options("pack")) for w in rows]

    @staticmethod
    def _prop_rows(repo: Repo | None) -> list[urwid.Widget]:
        if repo is None:
            return [urwid.Text(("hint", " (no repository selected)"))]
        refresh = "n/a" if repo.main else ("yes" if repo.refresh else "no")
        flags: list = [
            ("field", " Type: "), repo.sync_type or "—",
            ("field", "    Priority: "), repo.priority or "—",
            ("field", "    Auto-sync: "), repo.auto_sync or "—",
            ("field", "    Refresh: "), refresh,
            ("field", "    Default: "), "yes" if repo.main else "no",
        ]
        return [
            urwid.Text([("field", " Name      "), repo.name], wrap="clip"),
            urwid.Text([("field", " Sync URI  "), repo.sync_uri or "—"], wrap="clip"),
            urwid.Text([("field", " Location  "), repo.location or "—"], wrap="clip"),
            urwid.Text(flags, wrap="clip"),
        ]

    def _current_entry(self) -> tuple | None:
        if self._entries and 0 <= self._walker.focus < len(self._entries):
            return self._entries[self._walker.focus]
        return None

    def _current(self) -> Repo | None:
        entry = self._current_entry()
        return entry[1] if entry is not None and entry[0] == "repo" else None

    # -- key handling -------------------------------------------------------

    def handle_key(self, key):
        if key == "esc":
            self._leave()
        elif key == "r":
            self.app.run_async(self._load())
        elif key == "f10":
            self.app.run_async(self._accept())
        elif key == "f9":
            if not self._pending.is_empty:
                self._pending.clear()
                self._rebuild()
                self.app.notify("Pending changes discarded.")
        elif key == "a":
            self._enable()
        elif key == "A":
            self._add()
        elif key in ("d", "x", "t"):
            self._mark(key)
        else:
            return key
        return None

    def _leave(self) -> None:
        if self._pending.is_empty:
            self.app.pop()
            return
        n = self._pending.count()

        def discard():
            self._pending.clear()
            self.app.pop()   # modal
            self.app.pop()   # screen

        modal = Modal(
            self.app, f"You have {n} pending change{'s' if n != 1 else ''}.",
            [urwid.Text("Apply them (F10) before leaving, or discard?")],
            [("Discard & leave", discard), ("Keep editing", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 60), height=("relative", 35))

    def _mark(self, key: str) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        if entry[0] == "new":
            if key == "x":
                self._pending.cancel(entry[1])
                self._rebuild()
            else:
                self.app.notify("Staged new repository — press x to cancel it "
                                "(or F9 to discard all).", error=True)
            return
        repo = entry[1]
        if repo.main:
            self.app.notify("The main repository can't be changed here.", error=True)
            return
        if key == "d":
            self._pending.mark_state(repo.name, pending.DISABLE)
        elif key == "x":
            self._pending.mark_state(repo.name, pending.REMOVE)
        else:  # t
            self._pending.toggle_refresh(repo.name, repo.refresh)
        self._rebuild()

    def _known(self, name: str) -> bool:
        return (any(r.name == name for r in self._repos)
                or name in self._pending.state or name in self._pending.adds)

    def _enable(self) -> None:
        name = urwid.Edit("Repository name: ")

        def save():
            n = name.edit_text.strip()
            if not n:
                self.app.notify("A repository name is required.", error=True)
                return
            if self._known(n):
                self.app.notify(f"“{n}” is already listed or staged.", error=True)
                return
            self.app.pop()
            self._pending.mark_state(n, pending.ENABLE)
            self._rebuild()

        modal = Modal(self.app, "Stage enabling a known repository",
                      [urwid.Text("From the eselect repository list "
                                  "(fetched when applied)."), urwid.Divider(), name],
                      [("Stage", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 70), height=("relative", 50))

    def _add(self) -> None:
        name = urwid.Edit("Name: ")
        sync_type = urwid.Edit("Sync type: ", "git")
        uri = urwid.Edit("Sync URI: ")

        def save():
            n = name.edit_text.strip()
            if not n:
                self.app.notify("A repository name is required.", error=True)
                return
            if self._known(n):
                self.app.notify(f"“{n}” is already listed or staged.", error=True)
                return
            self.app.pop()
            self._pending.add(n, sync_type.edit_text.strip(), uri.edit_text.strip())
            self._rebuild()

        modal = Modal(self.app, "Stage adding a custom repository",
                      [name, sync_type, uri],
                      [("Stage", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 75), height=("relative", 55))

    # -- accept -------------------------------------------------------------

    async def _accept(self) -> None:
        if self._pending.is_empty:
            self.app.notify("No pending changes to apply.")
            return
        results: list[tuple[str, bool]] = []
        ops = self._pending.ordered_ops()
        if ops and not await self._run_ops(ops, results):
            return  # backend unavailable; nothing changed, keep marks
        if self._pending.touches_refresh_file():
            await self._apply_refresh(results)
        self._pending.clear()
        self._report(results)
        await self._load()

    async def _run_ops(self, ops, results: list) -> bool:
        backend = ReposBackend()
        try:
            await backend.connect()
        except Exception as exc:
            self.app.notify(f"Repository backend unavailable: {exc}", error=True)
            return False
        for kind, name, spec in ops:
            try:
                if kind == pending.ADD:
                    ok, _out = await backend.add(name, spec.sync_type, spec.uri)
                elif kind == pending.ENABLE:
                    ok, _out = await backend.enable(name)
                elif kind == pending.DISABLE:
                    ok, _out = await backend.disable(name)
                else:  # REMOVE
                    ok, _out = await backend.remove(name)
            except Exception:
                ok = False
            results.append((f"{name} ({kind})", ok))
        await backend.close()
        return True

    async def _apply_refresh(self, results: list) -> None:
        current_on = {r.name for r in self._repos if r.refresh and not r.main}
        final = self._pending.resolved_refresh(current_on)
        backend = PortageBackend()
        try:
            write = await self.app.run_blocking(lambda: writer.set_refresh(final))
            await backend.connect()
            ok = await backend.write_config([write])
        except Exception:
            ok = False
        else:
            await backend.close()
        results.append(("refresh-on-open", ok))

    def _report(self, results: list[tuple[str, bool]]) -> None:
        failed = [name for name, ok in results if not ok]
        total = len(results)
        if failed:
            self.app.notify(
                f"{total - len(failed)}/{total} applied — failed: {', '.join(failed)}",
                error=True)
        else:
            self.app.notify(f"Applied {total} change{'s' if total != 1 else ''}.")
