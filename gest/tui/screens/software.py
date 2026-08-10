"""Software Management (urwid): YaST sw_single-style two-pane browser.

Left: a Filter sidebar (view selector + search phrase + search-in fields).
Right: a package table with a pinned column header, a count line, and a live
detail pane. Mark packages (Space install/update, r remove), then Accept applies
them — installs first, then a depclean pass — through the organized per-package
AcceptRunScreen.
"""

from __future__ import annotations

import urwid

from gest.core.repos import reader as repos_reader
from gest.core.software import reader
from gest.core.software import selection as sel
from gest.core.software.backend_client import SoftwareBackend
from gest.core.software.model import PackageDetail
from gest.core.software.selection import Selection
from gest.tui.menubar import MenuBar, _Dropdown
from gest.tui.runtime import App, Screen, action_bar
from gest.tui.screens.accept import AcceptRunScreen
from gest.tui.screens.binhost import BinhostScreen
from gest.tui.screens.config import KeywordsScreen, UseFlagScreen
from gest.tui.screens.news import NewsScreen
from gest.tui.screens.sync import SyncScreen
from gest.tui.screens.update import UpdateScreen


def _row(text: str) -> urwid.Widget:
    icon = urwid.SelectableIcon(text, 0)
    icon.set_wrap_mode("clip")  # YaST-style: one line per package, no wrapping
    return urwid.AttrMap(icon, None, focus_map="focus")


def _fmt_size(n: int) -> str:
    if n <= 0:
        return "—"
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


_MENUS = [
    ("view", "View", [
        ("installed", "Installed packages", True),
        ("upgradable", "Updates available", True)]),
    ("config", "Configuration", [
        ("use", "USE flags", True), ("keywords", "Keywords / mask", True)]),
    ("binary", "Binary packages", [
        ("binhost", "Binary package sources & options…", True)]),
    ("deps", "Dependencies", [("check", "Check marked packages", True)]),
    ("extras", "Extras", [
        ("update", "System update", True), ("sync", "Sync tree", True),
        ("news", "Portage news", True)]),
]

# Filter views offered by the sidebar selector (id, label).
_VIEWS = [
    ("search", "Search"),
    ("provides", "Provides (file)"),
    ("categories", "Categories"),
    ("installed", "Installed"),
    ("upgradable", "Updates available"),
    ("world", "World set"),
]

# Search-phrase match modes (id, label).
_MODES = [
    ("contains", "Contains"),
    ("exact", "Exact"),
    ("regexp", "RegExp"),
]

# Per-package actions menu (id, label, enabled).
_ACTIONS = [
    ("install", "Install / Update", True),
    ("binpkg", "Install binary (only)", True),
    ("binpref", "Install (prefer binary)", True),
    ("remove", "Remove", True),
    ("use", "USE flags", True),
    ("keywords", "Keywords / mask", True),
]

_PKG_HEADER = f"   {'Name':<32} Summary"
_CAT_HEADER = "   Category"


class SoftwareScreen(Screen):
    # sidebar widget indices
    _VIEW_IDX = 0
    _SEARCH_W_IDX = 2
    _MODE_IDX = 3

    def __init__(self, app: App) -> None:
        self._cps: list[str] = []
        self._installed: list[bool] = []
        self._from_binary: list[bool] = []
        # cps with an available update — cached from the installed/world loads so
        # the ↑ flag shows in every view, not just the installed list.
        self._upgradable_cps: set[str] = set()
        self._summaries: list[str] = []
        self._categories: list[str] = []
        self._selection = Selection()
        self._view = "installed"
        self._mode = "contains"
        self._table_mode = "packages"  # "packages" | "categories"
        self._drilled: str | None = None

        # -- left: filter sidebar ------------------------------------------
        self._view_selector = _row(self._view_label())
        self._search = urwid.Edit("Search: ")
        self._mode_selector = _row(self._mode_label())
        self._ignore_cb = urwid.CheckBox("Ignore case", state=True)
        self._name_cb = urwid.CheckBox("Name", state=True)
        self._summary_cb = urwid.CheckBox("Summary")
        self._homepage_cb = urwid.CheckBox("Homepage")
        self._license_cb = urwid.CheckBox("License")
        self._description_cb = urwid.CheckBox("Description (slow)")
        self._sidebar = urwid.Pile([
            ("pack", self._view_selector),
            ("pack", urwid.Divider()),
            ("pack", self._search),
            ("pack", self._mode_selector),
            ("pack", self._ignore_cb),
            ("pack", urwid.Divider()),
            ("pack", urwid.Text(("hint", "Search in:"))),
            ("pack", self._name_cb),
            ("pack", self._summary_cb),
            ("pack", self._homepage_cb),
            ("pack", self._license_cb),
            ("pack", self._description_cb),
        ])
        sidebar_box = urwid.LineBox(
            urwid.Filler(self._sidebar, valign="top"), title="Filter")

        # -- right: table (with header) + count + detail -------------------
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._table = urwid.ListBox(self._walker)
        self._header = urwid.AttrMap(urwid.Text(_PKG_HEADER), "pane_title")
        self._table_frame = urwid.Frame(self._table, header=self._header)
        self._count = urwid.Text(" loading …")
        self._detail = urwid.Text("")
        detail_box = urwid.LineBox(
            urwid.Filler(self._detail, valign="top"), title="Detail")
        right = urwid.Pile([
            ("weight", 3, urwid.LineBox(self._table_frame, title="Packages")),
            ("pack", self._count),
            ("pack", urwid.Text(("hint", " [ Actions ▾ ]  press a")), ),
            ("weight", 2, detail_box),
        ])

        self._columns = urwid.Columns(
            [(34, sidebar_box), right], dividechars=1)
        self._menubar = MenuBar(app, _MENUS, self._on_menu, top=2)
        pile = urwid.Pile([
            ("pack", self._menubar),
            self._columns,
            ("pack", action_bar(["Cancel", "Accept"])),
        ])
        super().__init__(
            app, pile, title="Software Management",
            footer_keys=[
                ("Enter", "Search/Install"), ("Space", "Mark"), ("b", "Binary"),
                ("r", "Remove"), ("a", "Actions"), ("Tab", "Pane"), ("u", "USE"),
                ("k", "Keys"), ("F10", "Accept"), ("Esc", "Back"),
            ],
            help_text=(
                "Browse and manage Portage packages, YaST sw_single-style.\n\n"
                "Filter (left): pick a view (Search / Provides / Categories / "
                "Installed / Updates available / World), a search mode, and which "
                "fields to search.\n"
                "Table: ↑/↓ move · Space cycles the mark (none → install →\n"
                "binary-only → remove) · b jumps to binary-only · r jumps to\n"
                "remove · c clear marks · a Actions (adds 'prefer binary') · u USE.\n"
                "Status: i installed (from source) · ⓑ installed (from a binary "
                "package) · ↑ installed, a newer version is available (see the "
                "'Updates available' view). Marks: u update · + install · b "
                "binary-only · B prefer-binary · - remove.\n"
                "Binary installs use emerge --getbinpkg (configure sources under "
                "the Binary packages menu). F10 (Accept) applies all marks."
            ),
        )
        self._pile = pile
        self._pile.focus_position = 1              # the columns, not the menu
        self._columns.focus_position = 0           # the sidebar
        self._sidebar.focus_position = self._SEARCH_W_IDX
        urwid.connect_signal(self._walker, "modified", self._on_focus)
        app.run_async(self._open())

    # -- view selector ------------------------------------------------------

    def _view_label(self) -> str:
        title = dict(_VIEWS).get(self._view, "Search")
        return f" View: {title} ▾"

    def _update_view_label(self) -> None:
        self._view_selector.base_widget.set_text(self._view_label())

    def _open_view_menu(self) -> None:
        items = [(vid, label, True) for vid, label in _VIEWS]
        drop = _Dropdown(self.app, "view", items, self._on_view_pick)
        self.app.push_overlay(drop, align="left", left=2, valign="top", top=3,
                              width=drop.width, height=drop.height)

    def _on_view_pick(self, _menu_id: str, view_id: str) -> None:
        self._switch_view(view_id)

    # -- mode selector ------------------------------------------------------

    def _mode_label(self) -> str:
        title = dict(_MODES).get(self._mode, "Contains")
        return f" Mode: {title} ▾"

    def _open_mode_menu(self) -> None:
        items = [(mid, label, True) for mid, label in _MODES]
        drop = _Dropdown(self.app, "mode", items, self._on_mode_pick)
        self.app.push_overlay(drop, align="left", left=2, valign="top", top=6,
                              width=drop.width, height=drop.height)

    def _on_mode_pick(self, _menu_id: str, mode_id: str) -> None:
        self._mode = mode_id
        self._mode_selector.base_widget.set_text(self._mode_label())

    # -- actions menu -------------------------------------------------------

    def _open_actions_menu(self) -> None:
        if self._table_mode != "packages" or not self._cps:
            return
        drop = _Dropdown(self.app, "actions", _ACTIONS, self._on_action_pick)
        self.app.push_overlay(drop, align="left", left=38, valign="top", top=8,
                              width=drop.width, height=drop.height)

    def _on_action_pick(self, _menu_id: str, action_id: str) -> None:
        if not self._cps:
            return
        cp = self._cps[self._walker.focus]
        if action_id == "install":
            self._mark(sel.INSTALL)
        elif action_id == "binpkg":
            self._mark(sel.BINPKG)
        elif action_id == "binpref":
            self._mark(sel.BINPREF)
        elif action_id == "remove":
            self._mark(sel.REMOVE)
        elif action_id == "use":
            self.app.push(UseFlagScreen(self.app, cp))
        elif action_id == "keywords":
            self.app.push(KeywordsScreen(self.app, cp))

    def _switch_view(self, view: str) -> None:
        self._view = view
        self._drilled = None
        self._update_view_label()
        if view == "search":
            self._columns.focus_position = 0
            self._sidebar.focus_position = self._SEARCH_W_IDX
            term = self._search.edit_text.strip()
            if term:
                self.app.run_async(self._run_search(term))
            else:
                self._empty_table("Type a search phrase, then Enter.")
        elif view == "provides":
            self._columns.focus_position = 0
            self._sidebar.focus_position = self._SEARCH_W_IDX
            self._empty_table("Type a file path (e.g. /usr/bin/python), then Enter.")
        elif view == "categories":
            self.app.run_async(self._load_categories())
        elif view == "upgradable":
            self.app.run_async(self._load_upgradable())
        elif view == "world":
            self.app.run_async(self._load_world())
        else:
            self.app.run_async(self._load_installed())

    # -- loading ------------------------------------------------------------

    def _empty_table(self, hint: str) -> None:
        self._table_mode = "packages"
        self._cps, self._installed, self._summaries = [], [], []
        self._from_binary = []
        self._walker[:] = [urwid.Text(f" {hint}")]
        self._detail.set_text("")
        self._set_count("0 package(s)")

    async def _open(self) -> None:
        """First-open flow: refresh opted-in repos, then load the package list.

        Runs only once, when the screen is pushed — switching views afterwards
        calls the loaders directly and does not re-sync.
        """
        await self._refresh_repos()
        await self._load_installed()

    async def _refresh_repos(self) -> None:
        """Silently sync the repos flagged for refresh-on-open (never the main
        tree). Best-effort: a missing backend or denied auth just falls through
        to loading the (possibly staler) list rather than blocking the screen.
        """
        repos = await self.app.run_blocking(repos_reader.enabled_repos)
        names = [r.name for r in repos if r.refresh and not r.main and r.sync_uri]
        if not names:
            return
        plural = "y" if len(names) == 1 else "ies"
        self._set_count(f"Refreshing {len(names)} repositor{plural}…")
        self.app.refresh()
        backend = SoftwareBackend()
        try:
            await backend.connect()
            ok, out = await backend.sync_repos(names)
        except Exception as exc:
            self.app.notify(f"Repository refresh skipped: {exc}", error=True)
            await backend.close()
            return
        await backend.close()
        if not ok:
            tail = out.strip().splitlines()[-1] if out.strip() else "sync failed"
            self.app.notify(f"Some repositories didn't refresh — {tail}", error=True)

    def _note_upgradable(self, pkgs) -> None:
        """Cache the cps that have an available update, so the ↑ flag shows in
        every view. Refreshed whenever installed packages are (re)loaded."""
        self._upgradable_cps = {p.cp for p in pkgs if p.upgradable}

    async def _load_installed(self) -> None:
        pkgs = await self.app.run_blocking(reader.list_installed)
        self._note_upgradable(pkgs)
        self._fill([(p.cp, (p.description or "")[:60]) for p in pkgs],
                   [p.cp for p in pkgs], [True] * len(pkgs),
                   [p.from_binary for p in pkgs])
        n_up = len(self._upgradable_cps)
        suffix = f" · {n_up} with updates" if n_up else ""
        self._set_count(f"{len(pkgs)} installed package(s){suffix}")

    async def _load_upgradable(self) -> None:
        pkgs = await self.app.run_blocking(reader.list_upgradable)
        self._note_upgradable(pkgs)
        self._fill(
            [(p.cp, f"{p.version} → {p.available_version}  {(p.description or '')[:40]}")
             for p in pkgs],
            [p.cp for p in pkgs], [True] * len(pkgs),
            [p.from_binary for p in pkgs])
        self._set_count(
            f"{len(pkgs)} package(s) with updates available" if pkgs
            else "no updates available — everything is up to date")

    async def _load_world(self) -> None:
        pkgs = await self.app.run_blocking(reader.list_installed)
        self._note_upgradable(pkgs)
        world = [p for p in pkgs if p.world_member]
        self._fill([(p.cp, (p.description or "")[:60]) for p in world],
                   [p.cp for p in world], [True] * len(world),
                   [p.from_binary for p in world])
        n_up = sum(1 for p in world if p.upgradable)
        suffix = f" · {n_up} with updates" if n_up else ""
        self._set_count(f"{len(world)} @world package(s){suffix}")

    async def _load_categories(self) -> None:
        cats = await self.app.run_blocking(reader.list_categories)
        self._table_mode = "categories"
        self._categories = cats
        self._cps, self._installed, self._summaries = [], [], []
        self._from_binary = []
        self._header.base_widget.set_text(_CAT_HEADER)
        self._walker[:] = [_row(f"   {c}") for c in cats] or [urwid.Text(" (none)")]
        if cats:
            self._walker.set_focus(0)
        self._detail.set_text("Enter a category to list its packages.")
        self._set_count(f"{len(cats)} categories")

    async def _load_category(self, category: str) -> None:
        results = await self.app.run_blocking(
            lambda: reader.packages_in_category(category))
        self._drilled = category
        self._fill([(r.cp, (r.description or "")[:60]) for r in results],
                   [r.cp for r in results], [r.installed for r in results])
        self._set_count(f"{category}: {len(results)} package(s)")

    async def _run_file_search(self, path: str) -> None:
        results = await self.app.run_blocking(lambda: reader.search_file_owner(path))
        self._fill([(r.cp, (r.description or "")[:60]) for r in results],
                   [r.cp for r in results], [r.installed for r in results])
        self._set_count(
            f"{len(results)} package(s) own {path}" if results
            else f"no installed package owns {path}")

    async def _run_search(self, term: str) -> None:
        fields = []
        if self._name_cb.state:
            fields.append("name")
        if self._summary_cb.state:
            fields.append("summary")
        if self._homepage_cb.state:
            fields.append("homepage")
        if self._license_cb.state:
            fields.append("license")
        if self._description_cb.state:
            fields.append("description")
        mode, ignore_case = self._mode, self._ignore_cb.state
        results = await self.app.run_blocking(
            lambda: reader.search(term, fields=tuple(fields) or ("name",),
                                  mode=mode, ignore_case=ignore_case)
        )
        self._fill([(r.cp, (r.description or "")[:60]) for r in results],
                   [r.cp for r in results], [r.installed for r in results])
        self._set_count(f"{len(results)} package(s) found")

    def _fill(self, rows, cps, installed, from_binary=None) -> None:
        self._table_mode = "packages"
        self._header.base_widget.set_text(_PKG_HEADER)
        self._cps = cps
        self._installed = installed
        # Origin (source vs binary) is known only for the installed-derived
        # listings; other views leave it False. The ↑ update flag is driven by
        # the cross-view _upgradable_cps cache, so it works in every view.
        self._from_binary = from_binary if from_binary is not None else [False] * len(cps)
        self._summaries = [summary for _cp, summary in rows]
        widgets = [_row(self._row_text(i, cp, summary))
                   for i, (cp, summary) in enumerate(rows)]
        self._walker[:] = widgets or [urwid.Text(" (no packages)")]
        if cps:
            self._walker.set_focus(0)
        self.app.refresh()

    def _row_text(self, i: int, cp: str, summary: str):
        status = self._status_for(i, cp)
        line = f"{status} {cp:<32} {summary}"
        if status == "↑":                       # colour just the update flag
            return [("update", "↑"), line[1:]]
        return line

    def _status_for(self, i: int, cp: str) -> str:
        mark = self._selection.mark_of(cp)
        if mark == sel.INSTALL:
            return "u" if self._installed[i] else "+"
        if mark == sel.BINPKG:
            return "b"          # binary only
        if mark == sel.BINPREF:
            return "B"          # prefer binary
        if mark == sel.REMOVE:
            return "-"
        if self._installed[i]:
            if cp in self._upgradable_cps:
                return "↑"   # installed, a newer version is available (any view)
            return "ⓑ" if self._from_binary[i] else "i"   # ⓑ = from a binary pkg
        return " "

    # -- detail pane --------------------------------------------------------

    def _on_focus(self) -> None:
        if self._table_mode != "packages":
            return
        if self._cps and 0 <= self._walker.focus < len(self._cps):
            self.app.run_async(self._load_detail(self._cps[self._walker.focus]))

    async def _load_detail(self, cp: str) -> None:
        detail = await self.app.run_blocking(reader.get_package_detail, cp)
        self._detail.set_text(self._render_detail(cp, detail))
        self.app.refresh()

    def _render_detail(self, cp: str, d: PackageDetail | None):
        if d is None:
            return f"{cp}\n(no metadata)"
        rb = d.required_by
        if rb:
            rb_text = ", ".join(rb[:8])
            if len(rb) > 8:
                rb_text += f" … (+{len(rb) - 8} more)"
        else:
            rb_text = "—"
        return [
            ("title", f"{d.cp}"), f" — {d.description}\n\n",
            ("field", "Version: "), f"{d.available_version or '—'}   ",
            ("field", "Installed: "), f"{d.installed_version or '—'}   ",
            ("field", "Slot: "), f"{d.slot}\n",
            ("field", "Origin: "),
            (("binary package" if d.from_binary else "source build")
             if d.installed else "—") + "\n",
            ("field", "Size: "),
            f"{_fmt_size(d.installed_size)} installed · {_fmt_size(d.download_size)} download\n",
            ("field", "License: "), f"{d.license or '—'}\n",
            ("field", "Homepage: "), f"{d.homepage or '—'}\n",
            ("field", "Keywords: "), f"{d.keywords or '—'}\n",
            ("field", "Required by: "), rb_text,
        ]

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
        base = base.split("   ·   ")[0]
        self._set_count(base)

    # Space cycles the primary mark: none → install → binary-only → remove.
    # (r jumps to remove; b jumps to binary; Actions has prefer-binary.)
    _SPACE_CYCLE = (None, sel.INSTALL, sel.BINPKG, sel.REMOVE)

    def _toggle(self, remove: bool) -> None:
        self._mark(sel.REMOVE if remove else sel.INSTALL)

    def _cycle_mark(self) -> None:
        if self._table_mode != "packages" or not self._cps:
            return
        i = self._walker.focus
        cp = self._cps[i]
        cur = self._selection.mark_of(cp)
        idx = self._SPACE_CYCLE.index(cur) if cur in self._SPACE_CYCLE else 0
        self._selection.set(cp, self._SPACE_CYCLE[(idx + 1) % len(self._SPACE_CYCLE)])
        self._repaint_row(i, cp)

    def _mark(self, mark: str) -> None:
        if self._table_mode != "packages" or not self._cps:
            return
        i = self._walker.focus
        cp = self._cps[i]
        self._selection.toggle(cp, mark)
        self._repaint_row(i, cp)

    def _repaint_row(self, i: int, cp: str) -> None:
        self._walker[i].base_widget.set_text(self._row_text(i, cp, self._summaries[i]))
        self._refresh_count()

    # -- accept -------------------------------------------------------------

    def _accept(self) -> None:
        installs = self._selection.install_atoms()
        binpkgs = self._selection.binpkg_atoms()
        binprefs = self._selection.binpref_atoms()
        removes = self._selection.remove_atoms()
        if (not installs and not binpkgs and not binprefs and not removes
                and self._table_mode == "packages" and self._cps):
            installs = [self._cps[self._walker.focus]]
        if not installs and not binpkgs and not binprefs and not removes:
            self.app.notify("Mark packages with Space or r first.", error=True)
            return
        self.app.push(AcceptRunScreen(
            self.app, installs=installs, binpkgs=binpkgs, binprefs=binprefs,
            removes=removes, on_done=self._after))

    def _after(self) -> None:
        self._selection.clear()
        reader.invalidate_caches()  # deps/world changed → rebuild cached indexes
        self.app.run_async(self._load_installed())

    # -- menu bar -----------------------------------------------------------

    def _on_menu(self, menu_id: str, item_id: str) -> None:
        cp = self._cps[self._walker.focus] if (
            self._table_mode == "packages" and self._cps) else None
        if item_id == "installed":
            self._switch_view("installed")
        elif item_id == "upgradable":
            self._switch_view("upgradable")
        elif item_id == "use" and cp:
            self.app.push(UseFlagScreen(self.app, cp))
        elif item_id == "keywords" and cp:
            self.app.push(KeywordsScreen(self.app, cp))
        elif item_id == "check":
            self.app.run_async(self._check_marked())
        elif item_id == "binhost":
            self.app.push(BinhostScreen(self.app))
        elif item_id == "update":
            self.app.push(UpdateScreen(self.app))
        elif item_id == "sync":
            self.app.push(SyncScreen(self.app))
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

    def _context(self):
        in_menu = self._pile.focus_position == 0
        in_sidebar = (not in_menu) and self._columns.focus_position == 0
        in_table = (not in_menu) and self._columns.focus_position == 1
        sidebar_focus = self._sidebar.focus_position if in_sidebar else None
        return in_menu, in_sidebar, in_table, sidebar_focus

    def handle_key(self, key):
        _in_menu, in_sidebar, in_table, sidebar_focus = self._context()
        on_view = in_sidebar and sidebar_focus == self._VIEW_IDX
        on_search = in_sidebar and sidebar_focus == self._SEARCH_W_IDX
        on_mode = in_sidebar and sidebar_focus == self._MODE_IDX

        if key == "tab":
            self._cycle_pane()
            return None
        if key == "esc":
            if in_table and self._view == "categories" and self._drilled is not None:
                self.app.run_async(self._load_categories())
            else:
                self.app.pop()
            return None
        if on_view and key in ("enter", " ", "down"):
            self._open_view_menu()
            return None
        if on_mode and key in ("enter", " "):
            self._open_mode_menu()
            return None
        if key == "a" and in_table:
            self._open_actions_menu()
            return None
        if key == "f10":
            self._accept()
            return None
        if key == "enter":
            if on_search:
                term = self._search.edit_text.strip()
                if self._view == "provides":
                    if term:
                        self.app.run_async(self._run_file_search(term))
                elif term:
                    self.app.run_async(self._run_search(term))
                else:
                    self.app.run_async(self._load_installed())
            elif in_table and self._table_mode == "categories" and self._categories:
                self.app.run_async(self._load_category(self._categories[self._walker.focus]))
            elif in_table and self._cps:
                self.app.push(AcceptRunScreen(
                    self.app, installs=[self._cps[self._walker.focus]],
                    verb="Install", on_done=self._after))
            return None
        if key == "left" and in_table:
            self._columns.focus_position = 0
            return None
        if key == "right" and in_sidebar and not on_search:
            self._columns.focus_position = 1
            return None
        if in_table and self._table_mode == "packages":
            if key == " ":
                self._cycle_mark()       # none → install → binary-only → remove
                return None
            if key == "b":
                self._mark(sel.BINPKG)   # jump straight to binary-only
                return None
            if key == "r":
                self._toggle(remove=True)
                return None
            if key == "c":
                if not self._selection.is_empty:
                    self._selection.clear()
                    self._repaint()
                    self._refresh_count()
                return None
            if key == "u" and self._cps:
                self.app.push(UseFlagScreen(self.app, self._cps[self._walker.focus]))
                return None
            if key == "k" and self._cps:
                self.app.push(KeywordsScreen(self.app, self._cps[self._walker.focus]))
                return None
        return key

    def _cycle_pane(self) -> None:
        if self._pile.focus_position == 0:            # menu -> sidebar
            self._pile.focus_position = 1
            self._columns.focus_position = 0
        elif self._columns.focus_position == 0:       # sidebar -> table
            self._columns.focus_position = 1
        else:                                          # table -> menu
            self._pile.focus_position = 0

    def _repaint(self) -> None:
        for i, cp in enumerate(self._cps):
            self._walker[i].base_widget.set_text(self._row_text(i, cp, self._summaries[i]))
