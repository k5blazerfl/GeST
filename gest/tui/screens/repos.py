"""Software repositories (urwid): stage enable/add/disable/remove/refresh, then Accept.

A YaST-style layout: a columnar table (Change · Priority · AutoSync · Refresh ·
Name · Type · Sync URI) with pinned headers over a Properties panel. Reading is
unprivileged (/etc/portage/repos.conf). Changes are *staged* — nothing touches
the system until F10 Accept, which runs `eselect repository` through the
polkit-gated ReposBackend and writes the refresh-state file via the Portage
backend. `c` clears pending changes.
"""

from __future__ import annotations

import urwid

from gest.core.portage.backend_client import PortageBackend
from gest.core.repos import pending, reader, writer
from gest.core.repos.backend_client import ReposBackend
from gest.core.repos.reader import Repo
from gest.tui.runtime import App, Modal, Screen

# Table column widths (characters). Sync URI takes the remaining width and is
# clipped; the Properties panel shows it in full. The lead column shows either
# the ★ main marker or a staged-change tag like [disable] (mutually exclusive —
# the main repo can't be staged).
_FLAG_W = 11  # "★" or "[refresh-]"
_PRIO_W = 10
_AUTO_W = 9   # "AutoSync"
_REFRESH_W = 8  # "Refresh"
_NAME_W = 22
_TYPE_W = 8

_TRUTHY = {"yes", "true", "1", "on"}

# Staged-op → the tag shown in the Change column.
_OP_TAG = {pending.DISABLE: "disable", pending.REMOVE: "remove",
           pending.ENABLE: "enable", pending.ADD: "add"}


def _fmt(flag: str, prio: str, auto: str, refresh: str, name: str,
         stype: str, uri: str) -> str:
    if len(name) > _NAME_W - 1:
        name = name[: _NAME_W - 2] + "…"
    return (f"{flag:<{_FLAG_W}}{prio:<{_PRIO_W}}{auto:<{_AUTO_W}}"
            f"{refresh:<{_REFRESH_W}}{name:<{_NAME_W}}{stype:<{_TYPE_W}}{uri}")


def _repo_line(r: Repo, flag: str) -> str:
    auto = "x" if r.auto_sync.strip().lower() in _TRUTHY else ""
    # The main tree is barred from refresh-on-open (too slow — that's the Sync
    # Portage Tree tool's job); show a dash rather than a togglable cell.
    refresh = "—" if r.main else ("x" if r.refresh else "")
    lead = flag or ("★" if r.main else "")
    return _fmt(lead, r.priority or "—", auto, refresh, r.name,
                r.sync_type or "—", r.sync_uri or "—")


def _new_line(name: str, kind: str, spec: pending.AddSpec | None) -> str:
    stype = spec.sync_type if spec else "—"
    uri = spec.uri if spec else "(from eselect repository list)"
    return _fmt(f"[{_OP_TAG[kind]}]", "—", "", "", name, stype or "—", uri)


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
            urwid.Text(_fmt("Change", "Priority", "AutoSync", "Refresh", "Name",
                            "Type", "Sync URI"),
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

        body = urwid.Pile([("weight", 1, table), ("pack", props_box)])
        urwid.connect_signal(self._walker, "modified", self._on_focus)

        super().__init__(
            app, body,
            title="Repositories",
            footer_keys=[
                ("a", "Enable"), ("A", "Add"), ("d", "Disable"), ("x", "Remove"),
                ("t", "Refresh"), ("F10", "Accept"), ("c", "Clear"),
                ("r", "Reload"), ("Esc", "Back"),
            ],
            help_text=(
                "Software repositories configured in /etc/portage/repos.conf.\n\n"
                "Changes are STAGED, not applied immediately — mark what you want,\n"
                "then press F10 to Accept (apply) them all, or c to clear. The\n"
                "Change column shows each repo's pending mark; the status line\n"
                "counts them.\n\n"
                "The main (default) repository is marked ★ and is protected — it\n"
                "can't be disabled, removed, or refreshed-on-open.\n\n"
                "Columns:  Change · Priority · AutoSync (in emerge --sync) ·\n"
                "Refresh (sync on open) · Name · Type · Sync URI\n\n"
                "Refresh: when on (x), GeST syncs that repository each time Software\n"
                "Management opens. The ★ main tree is excluded — sync it with the\n"
                "Sync Portage Tree tool.\n\n"
                "a   stage enabling a known repository (from the eselect list)\n"
                "A   stage adding a custom repository (name / sync type / URI)\n"
                "d   stage disabling the highlighted repository\n"
                "x   stage removing it (deletes its files on Accept); on a staged\n"
                "    new repo, x cancels it\n"
                "t   toggle staged refresh-on-open for the highlighted repository\n"
                "F10 apply all staged changes    c  clear them    r  reload"
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
            rows.append(_row(_repo_line(r, self._flag_for(r))))
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
        self._update_status()
        self.app.refresh()

    def _flag_for(self, r: Repo) -> str:
        op = self._pending.state_of(r.name)
        if op in (pending.DISABLE, pending.REMOVE):
            return f"[{_OP_TAG[op]}]"
        ref = self._pending.refresh_of(r.name)
        if ref is not None:
            return "[refresh+]" if ref else "[refresh-]"
        return ""

    def _update_status(self) -> None:
        if self._pending.is_empty:
            self.set_status("")
            return
        n = self._pending.count()
        self.set_status(f"{n} pending change{'s' if n != 1 else ''} — "
                        "F10 Accept · c Clear")

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
            self.app.pop()
        elif key == "r":
            self.app.run_async(self._load())
        elif key == "f10":
            self.app.run_async(self._accept())
        elif key == "c":
            if not self._pending.is_empty:
                self._pending.clear()
                self._rebuild()
                self.app.notify("Pending changes cleared.")
        elif key == "a":
            self._enable()
        elif key == "A":
            self._add()
        elif key in ("d", "x", "t"):
            self._mark(key)
        else:
            return key
        return None

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
                                "(or c to clear all).", error=True)
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
