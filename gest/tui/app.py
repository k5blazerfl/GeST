"""GeST Textual application: the two-pane Control Center and module screens."""

from __future__ import annotations

from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    OptionList,
    Static,
)
from textual.widgets.option_list import Option

from gest import __version__
from gest.core.software import reader
from gest.tui.screens.install import InstallScreen
from gest.tui.screens.keywords import KeywordsScreen
from gest.tui.screens.news import NewsScreen
from gest.tui.screens.services import ServicesScreen
from gest.tui.screens.useflags import UseFlagScreen
from gest.tui.widgets.bracket_button import BracketButton
from gest.tui.widgets.function_bar import FunctionBar

# The Control Center groups modules under categories (left pane); the right
# pane lists the highlighted category's modules. ``enabled=False`` entries are
# visible-but-unimplemented so the roadmap stays legible.
CATEGORIES: list[tuple[str, list[tuple[str, str, bool]]]] = [
    ("Software", [
        ("software", "Software Management", True),
        ("update", "System Update", True),
        ("depclean", "Clean Up Packages", True),
        ("sync", "Sync Portage Tree", True),
        ("news", "Portage News", True),
    ]),
    ("Services", [
        ("services", "Services (OpenRC)", True),
    ]),
    ("Security and Users", [
        ("users", "Users & Groups", False),
    ]),
    ("Network", [
        ("network", "Network", False),
    ]),
]


class MainMenuScreen(Screen):
    """Landing screen: a YaST-style two-pane Control Center."""

    BINDINGS = [
        Binding("f1", "help", "Help"),
        Binding("f9", "app.quit", "Quit"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._cat_index = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("GeST Control Center", id="cc-header")
        with Horizontal(id="cc-body"):
            yield OptionList(
                *(Option(name, id=f"cat-{i}") for i, (name, _) in enumerate(CATEGORIES)),
                id="cc-categories",
            )
            yield OptionList(id="cc-modules")
        with Horizontal(id="cc-buttons"):
            yield BracketButton("Help", id="help")
            yield Static(id="cc-spacer")
            yield BracketButton("Run", id="run")
            yield BracketButton("Quit", id="quit")
        yield FunctionBar([("F1", "Help"), ("F9", "Quit")])

    def on_mount(self) -> None:
        self.title = "GeST"
        self._populate_modules(0)
        # Focus the category list so arrows work the instant the menu appears.
        self.query_one("#cc-categories", OptionList).focus()

    # -- population ---------------------------------------------------------

    def _populate_modules(self, cat_index: int) -> None:
        self._cat_index = cat_index
        modules = CATEGORIES[cat_index][1]
        ol = self.query_one("#cc-modules", OptionList)
        ol.clear_options()
        for key, title, enabled in modules:
            label = title if enabled else f"{title}  (coming soon)"
            ol.add_option(Option(label, id=f"mod-{key}"))
        if modules:
            ol.highlighted = 0

    # -- navigation ---------------------------------------------------------

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if event.option_list.id == "cc-categories":
            self._populate_modules(event.option_index)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "cc-categories":
            # Enter on a category drops into its module list (YaST behaviour).
            self.query_one("#cc-modules", OptionList).focus()
        else:
            self._launch(event.option.id.removeprefix("mod-"))

    def on_key(self, event: events.Key) -> None:
        cats = self.query_one("#cc-categories", OptionList)
        mods = self.query_one("#cc-modules", OptionList)
        if self.focused is cats and event.key == "right":
            mods.focus()
            event.stop()
        elif self.focused is mods and event.key in ("left", "escape"):
            cats.focus()
            event.stop()

    def on_bracket_button_pressed(self, event: BracketButton.Pressed) -> None:
        if event.button.id == "run":
            self._run_highlighted()
        elif event.button.id == "quit":
            self.app.exit()
        elif event.button.id == "help":
            self.action_help()

    def _run_highlighted(self) -> None:
        ol = self.query_one("#cc-modules", OptionList)
        if ol.highlighted is None:
            return
        opt = ol.get_option_at_index(ol.highlighted)
        self._launch(opt.id.removeprefix("mod-"))

    # -- launching ----------------------------------------------------------

    @staticmethod
    def _module_title(key: str) -> str:
        for _name, modules in CATEGORIES:
            for k, title, _enabled in modules:
                if k == key:
                    return title
        return key

    def _launch(self, key: str) -> None:
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
            self.app.notify(
                f"The {self._module_title(key)} module isn't implemented yet.",
                title="Coming soon",
                severity="warning",
            )

    def action_help(self) -> None:
        self.app.notify("Help isn't implemented yet.", severity="warning")

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
        return not (
            action == "focus_search"
            and self.focused is self.query_one("#search", Input)
        )

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
            "    ./bin/gest\n"
            "Do not launch it through a pipe or with a `!`/non-interactive shell.\n"
        )
        raise SystemExit(1)
    GestApp().run()


if __name__ == "__main__":
    main()
