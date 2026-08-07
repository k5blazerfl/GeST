"""GeST Textual application: a module menu and the software module screen."""

from __future__ import annotations

from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from gest import __version__
from gest.core.software import reader
from gest.tui.screens.install import InstallScreen
from gest.tui.screens.keywords import KeywordsScreen
from gest.tui.screens.news import NewsScreen
from gest.tui.screens.services import ServicesScreen
from gest.tui.screens.useflags import UseFlagScreen

# Modules offered on the main menu. Only "software" is wired up this release;
# the rest are visible-but-disabled placeholders so the roadmap is legible.
_MODULES = [
    ("software", "Software Management", "Browse, search and install packages (Portage)", True),
    ("update", "System Update", "Update all packages (emerge -uDN @world)", True),
    ("depclean", "Clean Up Packages", "Remove orphaned packages (emerge --depclean)", True),
    ("sync", "Sync Portage Tree", "Update the ebuild tree (emerge --sync)", True),
    ("news", "Portage News", "Read Gentoo news items (eselect news)", True),
    ("services", "Services (OpenRC)", "Start, stop and enable system services", True),
    ("users", "Users & Groups", "Manage user accounts and groups", False),
    ("network", "Network", "Configure interfaces and connections", False),
]


class MainMenuScreen(Screen):
    """Landing screen: pick an administration module."""

    BINDINGS = [Binding("q", "app.quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Center():
            with Vertical(id="menu-box"):
                yield Label("Select a module", id="menu-title")
                items = []
                for key, title, subtitle, enabled in _MODULES:
                    label = title if enabled else f"{title}  (coming soon)"
                    item = ListItem(
                        Label(label, classes="mod-title"),
                        Label(subtitle, classes="mod-sub"),
                        id=f"mod-{key}",
                    )
                    items.append(item)
                yield ListView(*items, id="module-list")
        yield Footer()

    def on_mount(self) -> None:
        # Focus the list explicitly so arrow keys work the instant the menu
        # appears (don't depend on auto-focus timing in a real terminal).
        self.query_one("#module-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        key = event.item.id.removeprefix("mod-")
        if key == "software":
            self.app.push_screen(SoftwareScreen())
        elif key == "update":
            self.app.push_screen(InstallScreen("@world", mode="world"))
        elif key == "depclean":
            self.app.push_screen(InstallScreen("", mode="depclean"))
        elif key == "services":
            self.app.push_screen(ServicesScreen())
        elif key == "sync":
            self.app.push_screen(InstallScreen("", mode="sync"))
        elif key == "news":
            self.app.push_screen(NewsScreen())
        else:
            title = next((t for k, t, *_ in _MODULES if k == key), key)
            self.app.notify(
                f"The {title} module isn't implemented yet.",
                title="Coming soon",
                severity="warning",
            )


class SoftwareScreen(Screen):
    """Portage software module: search available / list installed packages."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("q", "app.quit", "Quit"),
        Binding("/", "focus_search", "Search"),
        Binding("u", "edit_use", "USE flags"),
        Binding("k", "edit_keywords", "Keywords"),
        Binding("r", "remove_pkg", "Remove"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(
            placeholder="Search available packages — leave empty for installed",
            id="search",
        )
        yield Static("", id="status")
        table = DataTable(id="results", cursor_type="row", zebra_stripes=True)
        table.add_columns("Package", "Version", "Installed", "Description")
        yield table
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Software Management"
        self.query_one("#search", Input).focus()
        self.load_installed()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # Don't let the "/" quick-search binding swallow slashes the user is
        # typing into the search box (package atoms contain "/").
        if action == "focus_search" and self.focused is self.query_one("#search", Input):
            return False
        return True

    def on_key(self, event: events.Key) -> None:
        # Down from the search box drops into the results list, so the whole
        # screen is drivable from the keyboard without reaching for Tab.
        if event.key == "down" and self.focused is self.query_one("#search", Input):
            table = self.query_one("#results", DataTable)
            if table.row_count:
                table.focus()
                event.stop()

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        term = event.value.strip()
        if term:
            self.run_search(term)
        else:
            self.load_installed()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        # Enter (or click) on a package row opens its install preview.
        row = event.data_table.get_row(event.row_key)
        self.app.push_screen(InstallScreen(str(row[0])))

    def action_edit_use(self) -> None:
        # "u" on the highlighted package row opens its USE-flag editor.
        table = self.query_one("#results", DataTable)
        if table.row_count == 0:
            return
        cp = str(table.get_row_at(table.cursor_row)[0])
        self.app.push_screen(UseFlagScreen(cp))

    def action_edit_keywords(self) -> None:
        # "k" on the highlighted package row opens its keyword/mask editor.
        table = self.query_one("#results", DataTable)
        if table.row_count == 0:
            return
        cp = str(table.get_row_at(table.cursor_row)[0])
        self.app.push_screen(KeywordsScreen(cp))

    def action_remove_pkg(self) -> None:
        # "r" on the highlighted package previews a safe --depclean removal.
        table = self.query_one("#results", DataTable)
        if table.row_count == 0:
            return
        cp = str(table.get_row_at(table.cursor_row)[0])
        self.app.push_screen(InstallScreen(cp, mode="depclean"))

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    def _fill(self, rows: list[tuple[str, str, str, str]]) -> None:
        table = self.query_one("#results", DataTable)
        table.clear()
        for row in rows:
            table.add_row(*row)

    @work(thread=True, exclusive=True)
    def load_installed(self) -> None:
        pkgs = reader.list_installed()
        rows = [
            (
                p.cp,
                p.version,
                "★ world" if p.world_member else "yes",
                (p.description or "")[:70],
            )
            for p in pkgs
        ]
        self.app.call_from_thread(self._fill, rows)
        c = reader.counts()
        self.app.call_from_thread(
            self._set_status,
            f" {c['installed']} installed · {c['world']} in @world"
            "   —  Enter install · u USE · k keywords · r remove · / search",
        )

    @work(thread=True, exclusive=True)
    def run_search(self, term: str) -> None:
        self.app.call_from_thread(self._set_status, f" searching for “{term}” …")
        results = reader.search(term)
        rows = [
            (
                r.cp,
                r.best_version,
                r.installed_version or "—",
                (r.description or "")[:70],
            )
            for r in results
        ]
        self.app.call_from_thread(self._fill, rows)
        self.app.call_from_thread(
            self._set_status, f" {len(results)} match(es) for “{term}”"
        )


class GestApp(App):
    """The GeST application shell."""

    CSS_PATH = "app.tcss"
    TITLE = "GeST"
    SUB_TITLE = f"Gentoo System Tool {__version__}"

    def on_mount(self) -> None:
        self.push_screen(MainMenuScreen())


def main() -> None:
    import sys

    # A full-screen TUI needs a real interactive terminal. If stdin/stdout
    # are not a tty (piped, or launched through a non-interactive shell such
    # as the `!` prefix in another CLI), Textual would render but never
    # receive keystrokes — looking "dead". Fail loudly with guidance instead.
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.stderr.write(
            "gest: no interactive terminal detected — keyboard input will not work.\n"
            "Run it directly in a real terminal (e.g. a Konsole tab):\n"
            "    cd %s && ./bin/gest\n"
            "Do not launch it through a pipe or with a `!`/non-interactive shell.\n"
            % "/home/charron/GeST"
        )
        raise SystemExit(1)
    GestApp().run()


if __name__ == "__main__":
    main()
