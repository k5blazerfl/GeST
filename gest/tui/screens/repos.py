"""Software repositories (urwid): list configured repos, enable/add/disable/remove.

A YaST-style layout: a columnar table (Priority · Auto · Name · Type · Sync URI)
with pinned headers over a Properties panel that shows the focused repo's full
URI/location. Reading is unprivileged (/etc/portage/repos.conf); mutations run
`eselect repository` through the polkit-gated ReposBackend.
"""

from __future__ import annotations

import urwid

from gest.core.portage.backend_client import PortageBackend
from gest.core.repos import reader, writer
from gest.core.repos.backend_client import ReposBackend
from gest.core.repos.reader import Repo
from gest.tui.runtime import App, Modal, Screen

# Table column widths (characters). Sync URI takes the remaining width and is
# clipped; the Properties panel shows it in full.
_MARK_W = 2   # ★ main-repo marker
_PRIO_W = 10
_AUTO_W = 9   # "AutoSync"
_REFRESH_W = 8  # "Refresh"
_NAME_W = 22
_TYPE_W = 8

_TRUTHY = {"yes", "true", "1", "on"}


def _fmt(mark: str, prio: str, auto: str, refresh: str, name: str,
         stype: str, uri: str) -> str:
    if len(name) > _NAME_W - 1:
        name = name[: _NAME_W - 2] + "…"
    return (f"{mark:<{_MARK_W}}{prio:<{_PRIO_W}}{auto:<{_AUTO_W}}"
            f"{refresh:<{_REFRESH_W}}{name:<{_NAME_W}}{stype:<{_TYPE_W}}{uri}")


def _repo_line(r: Repo) -> str:
    mark = "★" if r.main else ""
    auto = "x" if r.auto_sync.strip().lower() in _TRUTHY else ""
    # The main tree is barred from refresh-on-open (too slow — that's the Sync
    # Portage Tree tool's job); show a dash rather than a togglable cell.
    refresh = "—" if r.main else ("x" if r.refresh else "")
    return _fmt(mark, r.priority or "—", auto, refresh, r.name,
                r.sync_type or "—", r.sync_uri or "—")


def _row(text: str) -> urwid.Widget:
    icon = urwid.SelectableIcon(text, 0)
    icon.set_wrap_mode("clip")   # keep rows to one line so columns stay aligned
    return urwid.AttrMap(icon, None, focus_map="focus")


class ReposScreen(Screen):
    def __init__(self, app: App) -> None:
        self._repos: list[Repo] = []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)

        header = urwid.AttrMap(
            urwid.Text(_fmt("", "Priority", "AutoSync", "Refresh", "Name",
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
                ("a", "Enable"), ("A", "Add"), ("d", "Disable"),
                ("x", "Remove"), ("t", "Refresh"), ("r", "Reload"),
                ("Esc", "Back"),
            ],
            help_text=(
                "Software repositories configured in /etc/portage/repos.conf.\n\n"
                "The main (default) repository is marked ★ and is protected — it\n"
                "can't be disabled, removed, or refreshed-on-open here.\n\n"
                "Columns:  Priority · AutoSync (in emerge --sync) · Refresh\n"
                "(sync on open) · Name · Type · Sync URI\n"
                "The Properties panel shows the focused repo's full URI and\n"
                "on-disk location.\n\n"
                "Refresh: when marked (x), GeST syncs that repository each time\n"
                "Software Management opens, so its package list is up to date. The\n"
                "★ main tree is excluded — sync it with the Sync Portage Tree tool.\n\n"
                "a   enable a known repository (from the eselect repository list)\n"
                "A   add a custom repository (name / sync type / URI)\n"
                "d   disable the highlighted repository\n"
                "x   remove the highlighted repository and delete its files\n"
                "t   toggle refresh-on-open for the highlighted repository\n"
                "r   reload the list"
            ),
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        self._repos = await self.app.run_blocking(reader.enabled_repos)
        rows = [_row(_repo_line(r)) for r in self._repos] \
            or [urwid.Text(" (no repositories configured)")]
        self._walker[:] = rows
        if self._repos:
            self._walker.set_focus(0)
        self._render_props()
        self.app.refresh()

    # -- properties panel ---------------------------------------------------

    def _on_focus(self) -> None:
        self._render_props()

    def _render_props(self) -> None:
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

    def _current(self) -> Repo | None:
        if self._repos and 0 <= self._walker.focus < len(self._repos):
            return self._repos[self._walker.focus]
        return None

    async def _call(self, action) -> None:
        backend = ReposBackend()
        try:
            await backend.connect()
            ok, out = await action(backend)
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        self.app.notify(out.splitlines()[-1] if out else ("done" if ok else "failed"),
                        error=not ok)
        await self._load()

    def handle_key(self, key):
        repo = self._current()
        if key == "esc":
            self.app.pop()
        elif key == "a":
            self._enable()
        elif key == "A":
            self._add()
        elif key == "r":
            self.app.run_async(self._load())
        elif key == "d" and repo is not None:
            if repo.main:
                self.app.notify("The main repository can't be disabled.", error=True)
            else:
                self.app.run_async(self._call(lambda b: b.disable(repo.name)))
        elif key == "x" and repo is not None:
            if repo.main:
                self.app.notify("The main repository can't be removed.", error=True)
            else:
                self._confirm_remove(repo.name)
        elif key == "t" and repo is not None:
            self._toggle_refresh(repo)
        else:
            return key
        return None

    def _toggle_refresh(self, repo: Repo) -> None:
        if repo.main:
            self.app.notify("The main repository can't be refreshed on open; "
                            "sync it with the Sync Portage Tree tool.", error=True)
            return
        on = not repo.refresh
        # The desired full selection: every currently-flagged (non-main) repo,
        # with this one toggled. Persisted wholesale to GeST's state file.
        names = {r.name for r in self._repos if r.refresh and not r.main}
        names.add(repo.name) if on else names.discard(repo.name)
        self.app.run_async(self._apply_refresh(names, repo, on))

    async def _apply_refresh(self, names: set[str], repo: Repo, on: bool) -> None:
        write = await self.app.run_blocking(lambda: writer.set_refresh(names))
        backend = PortageBackend()
        try:
            await backend.connect()
            ok = await backend.write_config([write])
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        if ok:
            self.app.notify(
                f"{repo.name}: refresh-on-open {'enabled' if on else 'disabled'}")
        else:
            self.app.notify("change was not applied", error=True)
        await self._load()

    def _enable(self) -> None:
        name = urwid.Edit("Repository name: ")

        def save():
            n = name.edit_text.strip()
            if not n:
                self.app.notify("A repository name is required.", error=True)
                return
            self.app.pop()
            self.app.run_async(self._call(lambda b: b.enable(n)))

        modal = Modal(self.app, "Enable a known repository",
                      [urwid.Text("From the eselect repository list "
                                  "(this may fetch the list)."), urwid.Divider(), name],
                      [("Enable", save), ("Cancel", self.app.pop)])
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
            self.app.pop()
            self.app.run_async(self._call(
                lambda b: b.add(n, sync_type.edit_text.strip(), uri.edit_text.strip())))

        modal = Modal(self.app, "Add a custom repository",
                      [name, sync_type, uri],
                      [("Add", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 75), height=("relative", 55))

    def _confirm_remove(self, name: str) -> None:
        def do():
            self.app.pop()
            self.app.run_async(self._call(lambda b: b.remove(name)))

        modal = Modal(self.app,
                      f"Remove repository “{name}” and delete its files?", [],
                      [("Remove", do), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 65), height=("relative", 40))
