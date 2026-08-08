"""Software repositories (urwid): list enabled repos, enable/add/disable/remove.

Reading is unprivileged (/etc/portage/repos.conf); mutations run
`eselect repository` through the polkit-gated ReposBackend.
"""

from __future__ import annotations

import urwid

from gest.core.repos import reader
from gest.core.repos.backend_client import ReposBackend
from gest.core.repos.reader import Repo
from gest.tui.runtime import App, Modal, Screen


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


class ReposScreen(Screen):
    def __init__(self, app: App) -> None:
        self._repos: list[Repo] = []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, urwid.LineBox(self._list, title="Software repositories"),
            title="Repositories",
            footer_keys=[
                ("a", "Enable"), ("A", "Add"), ("d", "Disable"),
                ("x", "Remove"), ("Esc", "Back"),
            ],
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        self._repos = await self.app.run_blocking(reader.enabled_repos)
        rows = [
            _row(f"{('★ ' if r.main else '  ')}{r.name:<18} {r.sync_type:<6} {r.sync_uri}")
            for r in self._repos
        ] or [urwid.Text(" (none)")]
        self._walker[:] = rows
        if self._repos:
            self._walker.set_focus(0)
        self.app.refresh()

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
        else:
            return key
        return None

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
