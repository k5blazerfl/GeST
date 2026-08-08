"""GeST TUI entry point (`gest`).

A urwid frontend over the frontend-agnostic ``gest.core`` modules. Run in a
real terminal.
"""

from __future__ import annotations

import sys

from gest.tui.runtime import App
from gest.tui.screens.menu import MenuScreen


def main() -> None:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.stderr.write(
            "gest: no interactive terminal detected — run it in a real terminal.\n"
        )
        raise SystemExit(1)
    app = App()
    app.run(MenuScreen(app))


if __name__ == "__main__":
    main()
