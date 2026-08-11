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
from gest.core.portage.write import ConfigWrite
from gest.core.repos import commands, edit, pending, reader, writer
from gest.core.repos import disabled as disabled_state
from gest.core.repos.backend_client import ReposBackend
from gest.core.repos.reader import Repo
from gest.tui.runtime import App, Modal, Screen, action_bar
from gest.tui.screens.deploykey import DeployKeyScreen
from gest.tui.screens.mirrors import MirrorScreen

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
_EDIT_GLYPH = "*"   # a staged edit of an existing repo's fields


def _fmt(mark: str, name: str, auto: str, refresh: str,
         stype: str, uri: str) -> str:
    if len(name) > _NAME_W - 1:
        name = name[: _NAME_W - 2] + "…"
    return (f"{mark:<{_MARK_W}}{name:<{_NAME_W}}{auto:<{_AUTO_W}}"
            f"{refresh:<{_REFRESH_W}}{stype:<{_TYPE_W}}{uri}")


def _repo_line(r: Repo, mark: str, refresh_cell: str) -> str:
    auto = "x" if r.auto_sync.strip().lower() in _TRUTHY else ""
    # Lead column: a staged mark takes priority, else ★ main / D disabled / blank.
    lead = mark or ("★" if r.main else ("D" if not r.enabled else ""))
    return _fmt(lead, r.name, auto, refresh_cell,
                r.sync_type or "—", r.sync_uri or "—")


def _new_line(name: str, kind: str, spec: pending.AddSpec | None) -> str:
    stype = spec.sync_type if spec else "—"
    uri = spec.uri if spec else "(from eselect repository list)"
    return _fmt(_STATE_GLYPH[kind], name, "", "", stype or "—", uri)


def _row(text: str, attr: str | None = None) -> urwid.Widget:
    icon = urwid.SelectableIcon(text, 0)
    icon.set_wrap_mode("clip")   # keep rows to one line so columns stay aligned
    return urwid.AttrMap(icon, attr, focus_map="focus")   # attr="dim" greys it


class ReposScreen(Screen):
    def __init__(self, app: App) -> None:
        self._repos: list[Repo] = []      # enabled repos, then disabled (greyed)
        self._disabled: list[Repo] = []   # the disabled subset (with saved sync info)
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
                ("a", "Enable"), ("A", "Add"), ("e", "Edit"), ("d", "Disable"),
                ("x", "Remove"), ("t", "Refresh"), ("m", "Mirror"),
                ("k", "SSH key"), ("F10", "Accept"), ("F9", "Cancel"),
                ("r", "Reload"), ("Esc", "Back"),
            ],
            help_text=(
                "Software repositories configured in /etc/portage/repos.conf.\n\n"
                "Editing is transactional: changes are STAGED as a mark, not applied\n"
                "immediately —\n"
                "  +  enable / add    *  edit    ~  disable    -  remove\n"
                "shown in the leftmost column (a staged refresh shows + / - in the\n"
                "Refresh column). The count line and [Accept] button sit below the\n"
                "list. F10 (Accept) applies every staged change; F9 (Cancel)\n"
                "discards them; a key pressed twice on a row clears its mark.\n\n"
                "Disabled repositories stay in the list, greyed out and flagged D in\n"
                "the leftmost column — GeST saves a disabled repo's sync info so you\n"
                "can re-enable it without retyping the URI (press a on the D row; x\n"
                "forgets it).\n\n"
                "The main (default) repository is flagged ★ and is protected — it\n"
                "can't be disabled, removed, or refreshed-on-open. Its rsync mirror\n"
                "can be changed though: focus the ★ row and press m to pick a\n"
                "geographically near Gentoo rotation (or a custom rsync URI).\n\n"
                "Columns:  Name · AutoSync (in emerge --sync) · Refresh (sync on\n"
                "open) · Type · Sync URI. Refresh: when on (x), GeST syncs that repo\n"
                "each time Software Management opens; the ★ main tree is excluded —\n"
                "sync it with the Sync Portage Tree tool.\n\n"
                "a  enable — on a greyed (disabled) repo, re-enables it; otherwise\n"
                "   stage enabling a known repository by name (from the eselect list)\n"
                "A  stage adding a custom repository (name / sync type / URI)\n"
                "e  stage editing an enabled repo's sync type / URI / priority\n"
                "d  stage disabling (keeps files + saves info)    x  remove — on an\n"
                "   enabled repo deletes its files; on a disabled one forgets it\n"
                "t  toggle refresh-on-open    m  change ★ main-repo mirror\n"
                "k  SSH deploy key — for syncing a private GitHub git overlay\n"
                "F10 Accept    F9 Cancel    r  reload"
            ),
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        enabled = await self.app.run_blocking(reader.enabled_repos)
        disabled = await self.app.run_blocking(reader.disabled_repos)
        names = {r.name for r in enabled}
        self._disabled = [r for r in disabled if r.name not in names]
        self._repos = enabled + self._disabled     # disabled shown last, greyed
        self._rebuild()

    # -- rendering ----------------------------------------------------------

    def _rebuild(self) -> None:
        """Rebuild the row list from repos + pending, preserving focus."""
        focus = self._walker.focus or 0
        rows: list[urwid.Widget] = []
        entries: list[tuple | None] = []
        for r in self._repos:
            attr = None if r.enabled else "dim"   # greyed out when disabled
            rows.append(_row(_repo_line(r, self._mark_for(r), self._refresh_cell(r)),
                             attr))
            entries.append(("repo", r))
        existing = {r.name for r in self._repos}
        for name, spec in sorted(self._pending.adds.items()):
            rows.append(_row(_new_line(name, pending.ADD, spec)))
            entries.append(("new", name))
        for name, op in self._pending.state.items():
            # A brand-new by-name enable is its own row; re-enabling a disabled
            # repo shows on that repo's existing (greyed) row instead.
            if op == pending.ENABLE and name not in existing:
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
        """Leading mark glyph for a staged change on this repo, else ''."""
        op = self._pending.state_of(r.name)
        if op:
            return _STATE_GLYPH.get(op, "")
        if self._pending.edit_of(r.name) is not None:
            return _EDIT_GLYPH
        return ""

    def _refresh_cell(self, r: Repo) -> str:
        if not r.enabled:
            return ""          # disabled repos aren't synced
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
        refresh = "n/a" if not repo.enabled or repo.main else (
            "yes" if repo.refresh else "no")
        flags: list = [
            ("field", " State: "), ("ok", "enabled") if repo.enabled else ("dim", "disabled"),
            ("field", "    Type: "), repo.sync_type or "—",
            ("field", "    Priority: "), repo.priority or "—",
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
            entry = self._current_entry()
            if entry is not None and entry[0] == "repo" and not entry[1].enabled:
                self._pending.mark_state(entry[1].name, pending.ENABLE)  # re-enable
                self._rebuild()
            else:
                self._enable()
        elif key == "A":
            self._add()
        elif key in ("e", "E"):
            self._edit()
        elif key in ("m", "M"):
            self._mirror()
        elif key in ("k", "K"):
            self.app.push(DeployKeyScreen(self.app))
        elif key in ("d", "x", "t"):
            self._mark(key)
        else:
            return key
        return None

    def _edit(self) -> None:
        repo = self._current()
        if repo is None or not repo.enabled:
            self.app.notify("Select an enabled repository to edit.", error=True)
            return
        staged = self._pending.edit_of(repo.name)
        sync_type = urwid.Edit("Sync type: ",
                               staged.sync_type if staged else repo.sync_type)
        uri = urwid.Edit("Sync URI:  ", staged.uri if staged else repo.sync_uri)
        priority = urwid.Edit("Priority:  ",
                              staged.priority if staged else repo.priority)

        def save():
            st = sync_type.edit_text.strip()
            u = uri.edit_text.strip()
            pr = priority.edit_text.strip()
            if not commands.valid_type(st):
                self.app.notify("A valid sync type is required (e.g. rsync, git).",
                                error=True)
                return
            if not commands.valid_uri(u):
                self.app.notify("A valid sync URI is required.", error=True)
                return
            if pr and not pr.isdigit():
                self.app.notify("Priority must be a whole number.", error=True)
                return
            self.app.pop()
            self._pending.edit(repo.name, st, u, pr)
            self._rebuild()

        modal = Modal(
            self.app, f"Edit repository “{repo.name}”",
            [urwid.Text(("hint", f" {repo.name}  ·  name is fixed")),
             urwid.Divider(), sync_type, uri, priority],
            [("Stage", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 75), height=("relative", 60))

    def _mirror(self) -> None:
        repo = self._current()
        if repo is None or not repo.main:
            self.app.notify("Select the ★ main repository to change its mirror.",
                            error=True)
            return
        if not self._pending.is_empty:
            self.app.notify("Apply or discard pending changes first (F10 / F9).",
                            error=True)
            return
        self.app.push(MirrorScreen(
            self.app, repo=repo.name, current=repo.sync_uri,
            on_done=lambda: self.app.run_async(self._load())))

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
        if not repo.enabled:
            if key == "x":
                self._pending.mark_state(repo.name, pending.REMOVE)   # forget it
                self._rebuild()
            else:
                self.app.notify("This repository is disabled — press a to re-enable "
                                "it, or x to forget it.", error=True)
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

    @staticmethod
    def _to_disabled(repo: Repo) -> disabled_state.DisabledRepo:
        return disabled_state.DisabledRepo(repo.name, repo.sync_type,
                                           repo.sync_uri, repo.priority)

    async def _accept(self) -> None:
        if self._pending.is_empty:
            self.app.notify("No pending changes to apply.")
            return
        by_name = {r.name: r for r in self._repos}
        ops = self._pending.ordered_ops()
        results: list[tuple[str, bool]] = []
        initial = [self._to_disabled(r) for r in self._disabled]
        final_disabled = list(initial)

        # Only "forget a disabled repo" (REMOVE on a disabled row) needs no eselect.
        needs_eselect = any(
            not self._is_forget(kind, name, by_name) for kind, name, _s in ops)
        backend = ReposBackend()
        if needs_eselect:
            try:
                await backend.connect()
            except Exception as exc:
                self.app.notify(f"Repository backend unavailable: {exc}", error=True)
                return
        for kind, name, spec in ops:
            ok, final_disabled = await self._apply_op(
                backend, kind, name, spec, by_name.get(name), final_disabled)
            results.append((f"{name} ({kind})", ok))
        if needs_eselect:
            await backend.close()

        await self._write_state(initial, final_disabled, results)
        self._pending.clear()
        self._report(results)
        await self._load()

    @staticmethod
    def _is_forget(kind: str, name: str, by_name: dict) -> bool:
        repo = by_name.get(name)
        return kind == pending.REMOVE and repo is not None and not repo.enabled

    async def _apply_op(self, backend, kind, name, spec, repo, final_disabled):
        """Run one op via eselect (as needed) and return (ok, updated disabled list)."""
        try:
            if kind == pending.ADD:
                ok, _ = await backend.add(name, spec.sync_type, spec.uri)
            elif kind == pending.ENABLE:
                if repo is not None and not repo.enabled:      # re-enable a disabled repo
                    if repo.sync_uri:
                        ok, _ = await backend.add(name, repo.sync_type or "git",
                                                  repo.sync_uri)
                    else:
                        ok, _ = await backend.enable(name)
                    if ok:
                        final_disabled = disabled_state.without(final_disabled, name)
                else:                                          # brand-new known repo
                    ok, _ = await backend.enable(name)
            elif kind == pending.DISABLE:                      # enabled -> disable + save
                ok, _ = await backend.disable(name)
                if ok and repo is not None:
                    final_disabled = disabled_state.upsert(
                        final_disabled, self._to_disabled(repo))
            elif repo is not None and not repo.enabled:        # REMOVE: forget it
                final_disabled = disabled_state.without(final_disabled, name)
                ok = True
            else:                                              # REMOVE: delete files
                ok, _ = await backend.remove(name)
                if ok:
                    final_disabled = disabled_state.without(final_disabled, name)
        except Exception:
            ok = False
        return ok, final_disabled

    async def _write_state(self, initial, final_disabled, results: list) -> None:
        """Persist disabled/refresh state plus any repo edits (one batched write)."""
        def key(rows):
            return sorted((d.name, d.sync_type, d.sync_uri, d.priority) for d in rows)

        builders: list[tuple[str, object]] = []
        if key(final_disabled) != key(initial):
            builders.append(("disabled", lambda: writer.set_disabled(final_disabled)))
        if self._pending.touches_refresh_file():
            current_on = {r.name for r in self._repos
                          if r.refresh and r.enabled and not r.main}
            final = self._pending.resolved_refresh(current_on)
            builders.append(("refresh-on-open", lambda: writer.set_refresh(final)))
        writes = [await self.app.run_blocking(fn) for _label, fn in builders]
        labels = [label for label, _fn in builders]
        for name, spec in self._pending.edits.items():           # existing-repo edits
            path, text = await self.app.run_blocking(edit.locate, None, name)
            fields = {"sync-type": spec.sync_type, "sync-uri": spec.uri,
                      "priority": spec.priority}
            writes.append(ConfigWrite(path, edit.set_fields(text, name, fields)))
            labels.append(f"{name} (edit)")
        if not writes:
            return
        backend = PortageBackend()
        try:
            await backend.connect()
            ok = await backend.write_config(writes)
        except Exception:
            ok = False
        else:
            await backend.close()
        results += [(label, ok) for label in labels]

    def _report(self, results: list[tuple[str, bool]]) -> None:
        failed = [name for name, ok in results if not ok]
        total = len(results)
        if failed:
            self.app.notify(
                f"{total - len(failed)}/{total} applied — failed: {', '.join(failed)}",
                error=True)
        else:
            self.app.notify(f"Applied {total} change{'s' if total != 1 else ''}.")
