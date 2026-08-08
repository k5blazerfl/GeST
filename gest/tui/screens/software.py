"""Software Management (urwid): search / list, live detail, transactional marks.

Mark packages (Space install/update, r remove), then Accept applies them —
installs first, then a depclean pass — through the streaming ApplyScreen. USE /
keyword editing and the dropdown menu bar are follow-ups; the core browse +
transactional flow lives here.
"""

from __future__ import annotations

import urwid

from gest.core.software import reader
from gest.core.software.model import PackageDetail
from gest.core.software.selection import Selection
from gest.tui.menubar import MenuBar
from gest.tui.runtime import App, Screen
from gest.tui.screens.apply import (
    ApplyScreen,
    install_plan,
    remove_plan,
    sync_plan,
    world_plan,
)
from gest.tui.screens.config import KeywordsScreen, UseFlagScreen
from gest.tui.screens.news import NewsScreen


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


_MENUS = [
    ("view", "View", [("installed", "Installed packages", True)]),
    ("config", "Configuration", [
        ("use", "USE flags", True), ("keywords", "Keywords / mask", True)]),
    ("deps", "Dependencies", [("check", "Check marked packages", True)]),
    ("extras", "Extras", [
        ("update", "System update", True), ("sync", "Sync tree", True),
        ("news", "Portage news", True)]),
]


class SoftwareScreen(Screen):
    _SEARCH_IDX = 1
    _TABLE_IDX = 4

    def __init__(self, app: App) -> None:
        self._cps: list[str] = []
        self._installed: list[bool] = []
        self._summaries: list[str] = []
        self._selection = Selection()

        self._search = urwid.Edit("Search: ")
        self._name_cb = urwid.CheckBox("Name", state=True)
        self._summary_cb = urwid.CheckBox("Summary")
        search_in = urwid.Columns([
            ("pack", urwid.Text("Search in: ")),
            ("pack", self._name_cb),
            ("pack", urwid.Text("  ")),
            ("pack", self._summary_cb),
        ])
        self._count = urwid.Text(" loading …")
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._table = urwid.ListBox(self._walker)
        self._detail = urwid.Text("")
        detail_box = urwid.LineBox(
            urwid.Filler(self._detail, valign="top"), title="Detail"
        )
        self._menubar = MenuBar(app, _MENUS, self._on_menu, top=2)
        pile = urwid.Pile([
            ("pack", self._menubar),
            ("pack", self._search),
            ("pack", search_in),
            ("pack", self._count),
            ("weight", 3, urwid.LineBox(self._table, title="Packages")),
            ("weight", 2, detail_box),
        ])
        super().__init__(
            app, pile, title="Software Management",
            footer_keys=[
                ("Enter", "Search/Install"), ("Space", "Mark"), ("r", "Remove"),
                ("c", "Clear"), ("u", "USE"), ("k", "Keywords"),
                ("F10", "Accept"), ("↑", "Menu"), ("Esc", "Back"),
            ],
        )
        self._pile = pile
        self._pile.focus_position = self._SEARCH_IDX  # land on search, not the menu
        urwid.connect_signal(self._walker, "modified", self._on_focus)
        app.run_async(self._load_installed())

    # -- loading ------------------------------------------------------------

    async def _load_installed(self) -> None:
        pkgs = await self.app.run_blocking(reader.list_installed)
        self._fill([(p.cp, (p.description or "")[:60]) for p in pkgs],
                   [p.cp for p in pkgs], [True] * len(pkgs))
        self._set_count(f"{len(pkgs)} installed package(s)")

    async def _run_search(self, term: str) -> None:
        fields = []
        if self._name_cb.state:
            fields.append("name")
        if self._summary_cb.state:
            fields.append("summary")
        results = await self.app.run_blocking(
            lambda: reader.search(term, fields=tuple(fields) or ("name",))
        )
        self._fill([(r.cp, (r.description or "")[:60]) for r in results],
                   [r.cp for r in results], [r.installed for r in results])
        self._set_count(f"{len(results)} package(s) found")

    def _fill(self, rows, cps, installed) -> None:
        self._cps = cps
        self._installed = installed
        self._summaries = [summary for _cp, summary in rows]
        widgets = [_row(self._row_text(i, cp, summary))
                   for i, (cp, summary) in enumerate(rows)]
        self._walker[:] = widgets or [urwid.Text(" (no packages)")]
        if cps:
            self._walker.set_focus(0)
        self.app.refresh()

    def _row_text(self, i: int, cp: str, summary: str) -> str:
        return f"{self._status_for(i, cp)} {cp:<32} {summary}"

    def _status_for(self, i: int, cp: str) -> str:
        mark = self._selection.mark_of(cp)
        if mark == "install":
            return "u" if self._installed[i] else "+"
        if mark == "remove":
            return "-"
        return "i" if self._installed[i] else " "

    # -- detail pane --------------------------------------------------------

    def _on_focus(self) -> None:
        if self._cps and 0 <= self._walker.focus < len(self._cps):
            self.app.run_async(self._load_detail(self._cps[self._walker.focus]))

    async def _load_detail(self, cp: str) -> None:
        detail = await self.app.run_blocking(reader.get_package_detail, cp)
        self._detail.set_text(self._render_detail(cp, detail))
        self.app.refresh()

    def _render_detail(self, cp: str, d: PackageDetail | None) -> str:
        if d is None:
            return f"{cp}\n(no metadata)"
        return (
            f"{d.cp} — {d.description}\n"
            f"Version: {d.available_version or '—'}   Installed: {d.installed_version or '—'}"
            f"   Slot: {d.slot}\n"
            f"License: {d.license or '—'}\n"
            f"Homepage: {d.homepage or '—'}\n"
            f"Keywords: {d.keywords or '—'}"
        )

    # -- marks + count ------------------------------------------------------

    def _set_count(self, text: str) -> None:
        summary = self._selection.summary()
        if not self._selection.is_empty:
            text += f"   ·   {summary} (F10 Accept · c clear)"
        self._count.set_text(f" {text}")
        self._base_count = text
        self.app.refresh()

    def _refresh_count(self) -> None:
        base = getattr(self, "_base_count", "")
        # strip a previous selection suffix
        base = base.split("   ·   ")[0]
        self._set_count(base)

    def _toggle(self, remove: bool) -> None:
        if not self._cps:
            return
        i = self._walker.focus
        cp = self._cps[i]
        if remove:
            self._selection.toggle_remove(cp)
        else:
            self._selection.toggle_install(cp)
        self._walker[i].base_widget.set_text(self._row_text(i, cp, self._summaries[i]))
        self._refresh_count()

    # -- accept -------------------------------------------------------------

    def _accept(self) -> None:
        installs = self._selection.install_atoms()
        removes = self._selection.remove_atoms()
        if not installs and not removes and self._cps:
            installs = [self._cps[self._walker.focus]]
        if not installs and not removes:
            self.app.notify("Mark packages with Space or r first.", error=True)
            return
        plans = []
        if installs:
            plans.append(install_plan(installs))
        if removes:
            plans.append(remove_plan(removes))
        self.app.push(ApplyScreen(self.app, plans, verb="Accept", on_done=self._after))

    def _after(self) -> None:
        self._selection.clear()
        self.app.run_async(self._load_installed())

    # -- menu bar -----------------------------------------------------------

    def _on_menu(self, menu_id: str, item_id: str) -> None:
        cp = self._cps[self._walker.focus] if self._cps else None
        if item_id == "installed":
            self.app.run_async(self._load_installed())
        elif item_id == "use" and cp:
            self.app.push(UseFlagScreen(self.app, cp))
        elif item_id == "keywords" and cp:
            self.app.push(KeywordsScreen(self.app, cp))
        elif item_id == "check":
            self.app.run_async(self._check_marked())
        elif item_id == "update":
            self.app.push(ApplyScreen(self.app, [world_plan()], verb="System update"))
        elif item_id == "sync":
            self.app.push(ApplyScreen(self.app, [sync_plan()], verb="Sync"))
        elif item_id == "news":
            self.app.push(NewsScreen(self.app))

    async def _check_marked(self) -> None:
        from gest.core.software import preview
        atoms = self._selection.install_atoms()
        if not atoms:
            self.app.notify("No packages marked for install.")
            return
        result = await self.app.run_blocking(lambda: preview.preview_install_many(atoms))
        self.app.notify(result.summary)

    # -- keys ---------------------------------------------------------------

    def handle_key(self, key):
        focus_search = self._pile.focus_position == self._SEARCH_IDX
        if key == "esc":
            self.app.pop()
            return None
        if key == "enter":
            if focus_search:
                term = self._search.edit_text.strip()
                self.app.run_async(
                    self._run_search(term) if term else self._load_installed()
                )
            elif self._cps:
                self.app.push(ApplyScreen(
                    self.app, [install_plan([self._cps[self._walker.focus]])],
                    verb="Install"))
            return None
        if key == "f10":
            self._accept()
            return None
        if key == " " and not focus_search:
            self._toggle(remove=False)
            return None
        if key == "r" and not focus_search:
            self._toggle(remove=True)
            return None
        if key == "c" and not focus_search:
            if not self._selection.is_empty:
                self._selection.clear()
                self._repaint()
                self._refresh_count()
            return None
        if key == "u" and not focus_search and self._cps:
            self.app.push(UseFlagScreen(self.app, self._cps[self._walker.focus]))
            return None
        if key == "k" and not focus_search and self._cps:
            self.app.push(KeywordsScreen(self.app, self._cps[self._walker.focus]))
            return None
        return key

    def _repaint(self) -> None:
        for i, cp in enumerate(self._cps):
            self._walker[i].base_widget.set_text(self._row_text(i, cp, self._summaries[i]))
