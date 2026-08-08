"""Software Management — YaST sw_single-style master/detail screen.

Layout: a dropdown menu bar on top; a filter sidebar on the left (search + the
YaST "Search in" checkboxes); a package table top-right with a live count; and a
detail pane below it that refreshes as the cursor moves. Actions still work the
way they did — Enter previews an install, u/k edit config, r removes — and are
also reachable from the Configuration/Extras menus. (Transactional mark→Accept
lands in the next slice; for now Accept installs the highlighted package.)
"""

from __future__ import annotations

from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.coordinate import Coordinate
from textual.screen import Screen
from textual.widgets import Checkbox, DataTable, Header, Input, Static

from gest.core.software import preview, reader
from gest.core.software.model import PackageDetail
from gest.core.software.selection import Selection
from gest.tui.screens.install import InstallScreen
from gest.tui.screens.keywords import KeywordsScreen
from gest.tui.screens.news import NewsScreen
from gest.tui.screens.useflags import UseFlagScreen
from gest.tui.widgets.bracket_button import BracketButton
from gest.tui.widgets.function_bar import FunctionBar
from gest.tui.widgets.menu_bar import MenuBar

_MENUS = [
    ("deps", "Dependencies", [
        ("checknow", "Check marked packages", True),
        ("autocheck", "Automatic dependency check", False),
    ]),
    ("view", "View", [
        ("installed", "Installed packages", True),
        ("world", "@world set only", True),
    ]),
    ("config", "Configuration", [
        ("use", "USE flags…", True),
        ("keywords", "Keywords / mask…", True),
    ]),
    ("extras", "Extras", [
        ("update", "System update (@world)…", True),
        ("sync", "Sync Portage tree…", True),
        ("news", "Portage news…", True),
    ]),
]


class SoftwareScreen(Screen):
    """Portage software module: search / list packages with a live detail pane."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Cancel"),
        Binding("f9", "app.pop_screen", "Cancel"),
        Binding("f10", "accept", "Accept"),
        Binding("f1", "help", "Help"),
        Binding("q", "app.quit", "Quit"),
        Binding("space", "toggle_mark", "Mark"),
        Binding("c", "clear_marks", "Clear marks"),
        Binding("/", "focus_search", "Search"),
        Binding("u", "edit_use", "USE flags"),
        Binding("k", "edit_keywords", "Keywords"),
        Binding("r", "toggle_remove", "Remove mark"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._cps: list[str] = []
        self._installed: list[bool] = []
        self._base_count: str = ""
        self._selection = Selection()
        self._pending_removes: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield MenuBar(_MENUS, id="sw-menubar")
        with Horizontal(id="sw-body"):
            with Vertical(id="sw-filter"):
                yield Static("Filter", classes="filter-h")
                yield Input(placeholder="Search…", id="search")
                yield Checkbox("Ignore Case", value=True, disabled=True, id="ignore-case")
                yield Static("Search in", classes="filter-h")
                yield Checkbox("Name", value=True, id="in-name")
                yield Checkbox("Summary (slower)", value=False, id="in-summary")
                yield Checkbox("Keywords", value=False, disabled=True)
                yield Checkbox("Description", value=False, disabled=True)
                yield Checkbox("Provides", value=False, disabled=True)
                yield Checkbox("Required by", value=False, disabled=True)
            with Vertical(id="sw-main"):
                yield Static("", id="sw-count")
                table = DataTable(id="results", cursor_type="row", zebra_stripes=True)
                table.add_columns("S", "Package", "Summary")
                yield table
                yield VerticalScroll(Static("", id="sw-detail"), id="sw-detail-box")
        with Horizontal(id="sw-buttons"):
            yield BracketButton("Help", id="help")
            yield Static(id="sw-spacer")
            yield BracketButton("Cancel", id="cancel")
            yield BracketButton("Accept", id="accept")
        yield FunctionBar([("F1", "Help"), ("F9", "Cancel"), ("F10", "Accept")])

    def on_mount(self) -> None:
        self.title = "Software Management"
        self.query_one("#search", Input).focus()
        self.load_installed()

    # -- keyboard glue ------------------------------------------------------

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # Don't let "/" swallow slashes typed into the search box (atoms use /).
        return not (
            action == "focus_search"
            and self.focused is self.query_one("#search", Input)
        )

    def on_key(self, event: events.Key) -> None:
        table = self.query_one("#results", DataTable)
        if event.key == "down" and self.focused is self.query_one("#search", Input):
            if table.row_count:
                table.focus()
                event.stop()
        elif event.key == "space" and self.focused is table:
            self.action_toggle_mark()
            event.stop()
        elif event.key == "r" and self.focused is table:
            self.action_toggle_remove()
            event.stop()

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_help(self) -> None:
        self.app.notify("Help isn't implemented yet.", severity="warning")

    def action_accept(self) -> None:
        installs = self._selection.install_atoms()
        removes = self._selection.remove_atoms()
        if not installs and not removes:
            cp = self._current_cp()
            installs = [cp] if cp else []
        if not installs and not removes:
            self.app.notify("Mark packages with Space (install) or r (remove).",
                            severity="warning")
            return
        # Apply installs first, then removals — each as its own streamed screen.
        self._pending_removes = removes
        if installs:
            self.app.push_screen(
                InstallScreen("", mode="multi", atoms=installs), self._after_installs
            )
        else:
            self._start_removes()

    def _after_installs(self, _result=None) -> None:
        if self._pending_removes:
            self._start_removes()
        else:
            self._after_apply()

    def _start_removes(self) -> None:
        removes, self._pending_removes = self._pending_removes, []
        self.app.push_screen(
            InstallScreen("", mode="depclean-multi", atoms=removes), self._after_apply
        )

    def _after_apply(self, _result=None) -> None:
        self._selection.clear()
        self.load_installed()

    def _toggle_current(self, *, remove: bool) -> None:
        table = self.query_one("#results", DataTable)
        if not self._cps or table.cursor_row is None:
            return
        row = table.cursor_row
        if not (0 <= row < len(self._cps)):
            return
        cp = self._cps[row]
        if remove:
            self._selection.toggle_remove(cp)
        else:
            self._selection.toggle_install(cp)
        table.update_cell_at(Coordinate(row, 0), self._status_for(row))
        self._render_count()

    def action_toggle_mark(self) -> None:
        self._toggle_current(remove=False)

    def action_toggle_remove(self) -> None:
        self._toggle_current(remove=True)

    def action_clear_marks(self) -> None:
        if self._selection.is_empty:
            return
        self._selection.clear()
        self._repaint_status()
        self._render_count()

    def _status_for(self, row: int) -> str:
        mark = self._selection.mark_of(self._cps[row])
        if mark == "install":
            return "u" if self._installed[row] else "+"
        if mark == "remove":
            return "-"
        return "i" if self._installed[row] else " "

    def _repaint_status(self) -> None:
        table = self.query_one("#results", DataTable)
        for row in range(len(self._cps)):
            table.update_cell_at(Coordinate(row, 0), self._status_for(row))

    # -- current selection --------------------------------------------------

    def _current_cp(self) -> str | None:
        table = self.query_one("#results", DataTable)
        if not self._cps or table.cursor_row is None:
            return None
        if 0 <= table.cursor_row < len(self._cps):
            return self._cps[table.cursor_row]
        return None

    # -- input / rows -------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        term = event.value.strip()
        if term:
            self.run_search(term, self._search_fields())
        else:
            self.load_installed()

    def _search_fields(self) -> tuple[str, ...]:
        fields = []
        if self.query_one("#in-name", Checkbox).value:
            fields.append("name")
        if self.query_one("#in-summary", Checkbox).value:
            fields.append("summary")
        return tuple(fields) or ("name",)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        cp = self._current_cp()
        if cp is not None:
            self.app.push_screen(InstallScreen(cp))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if 0 <= event.cursor_row < len(self._cps):
            self.show_detail(self._cps[event.cursor_row])

    # -- menu bar -----------------------------------------------------------

    def on_menu_bar_selected(self, event: MenuBar.Selected) -> None:
        if event.item == "installed":
            self.load_installed()
        elif event.item == "world":
            self.load_installed(world_only=True)
        elif event.item == "use":
            self.action_edit_use()
        elif event.item == "keywords":
            self.action_edit_keywords()
        elif event.item == "update":
            self.app.push_screen(InstallScreen("@world", mode="world"))
        elif event.item == "sync":
            self.app.push_screen(InstallScreen("", mode="sync"))
        elif event.item == "news":
            self.app.push_screen(NewsScreen())
        elif event.item == "checknow":
            self.check_marked()
        else:
            self.app.notify("Not implemented yet.", severity="warning")

    def on_bracket_button_pressed(self, event: BracketButton.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "accept":
            self.action_accept()
        elif event.button.id == "help":
            self.action_help()

    # -- config actions -----------------------------------------------------

    def action_edit_use(self) -> None:
        cp = self._current_cp()
        if cp is not None:
            self.app.push_screen(UseFlagScreen(cp))

    def action_edit_keywords(self) -> None:
        cp = self._current_cp()
        if cp is not None:
            self.app.push_screen(KeywordsScreen(cp))

    # -- rendering ----------------------------------------------------------

    @work(thread=True, exclusive=True)
    def check_marked(self) -> None:
        atoms = self._selection.install_atoms()
        if not atoms:
            self.app.call_from_thread(
                self.app.notify, "No packages marked for install.",
                severity="warning")
            return
        result = preview.preview_install_many(atoms)
        self.app.call_from_thread(
            self.app.notify, result.summary, title="Dependency check",
            severity="information" if result.ok else "error")

    def _set_count(self, text: str) -> None:
        self._base_count = text
        self._render_count()

    def _render_count(self) -> None:
        text = self._base_count
        if not self._selection.is_empty:
            text += f"   ·   [b]{self._selection.summary()}[/b] (F10 Accept · c clear)"
        self.query_one("#sw-count", Static).update(text)

    def _fill(self, rows: list[tuple[str, str]], cps: list[str],
              installed: list[bool]) -> None:
        table = self.query_one("#results", DataTable)
        table.clear()
        self._cps = cps
        self._installed = installed
        for i, (cp, summary) in enumerate(rows):
            table.add_row(self._status_for(i), cp, summary)

    @work(thread=True, exclusive=True)
    def load_installed(self, world_only: bool = False) -> None:
        pkgs = reader.list_installed()
        if world_only:
            pkgs = [p for p in pkgs if p.world_member]
        rows = [(p.cp, (p.description or "")[:70]) for p in pkgs]
        cps = [p.cp for p in pkgs]
        installed = [True] * len(pkgs)
        self.app.call_from_thread(self._fill, rows, cps, installed)
        scope = "@world" if world_only else "installed"
        self.app.call_from_thread(self._set_count, f" {len(pkgs)} {scope} package(s)")

    @work(thread=True, exclusive=True)
    def run_search(self, term: str, fields: tuple[str, ...] = ("name",)) -> None:
        self.app.call_from_thread(self._set_count, f" searching for “{term}” …")
        results = reader.search(term, fields=fields)
        rows = [(r.cp, (r.description or "")[:70]) for r in results]
        cps = [r.cp for r in results]
        installed = [r.installed for r in results]
        self.app.call_from_thread(self._fill, rows, cps, installed)
        self.app.call_from_thread(self._set_count, f" {len(results)} package(s) found")

    @work(thread=True, exclusive=True)
    def show_detail(self, cp: str) -> None:
        detail = reader.get_package_detail(cp)
        self.app.call_from_thread(self._render_detail, cp, detail)

    def _render_detail(self, cp: str, detail: PackageDetail | None) -> None:
        pane = self.query_one("#sw-detail", Static)
        if detail is None:
            pane.update(f"[b]{cp}[/b]\n(no metadata)")
            return
        installed = detail.installed_version or "—"
        lines = [
            f"[b]{detail.cp}[/b] — {detail.description}",
            "",
            f"[b]Version:[/b] {detail.available_version or '—'}   "
            f"[b]Installed:[/b] {installed}   [b]Slot:[/b] {detail.slot}",
            f"[b]License:[/b] {detail.license or '—'}",
            f"[b]Homepage:[/b] {detail.homepage or '—'}",
            f"[b]Keywords:[/b] {detail.keywords or '—'}",
        ]
        pane.update("\n".join(lines))
