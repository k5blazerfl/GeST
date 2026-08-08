"""GeST urwid frontend entry point (`gest-uw`).

A parallel frontend during the Textual → urwid migration; renders the same
``gest.core`` modules. Run in a real terminal.
"""

from __future__ import annotations

import sys

from gest.uwui.runtime import App
from gest.uwui.screens.menu import MenuScreen


def main() -> None:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.stderr.write(
            "gest-uw: no interactive terminal detected — run it in a real terminal.\n"
        )
        raise SystemExit(1)
    app = App()
    app.run(MenuScreen(app))


if __name__ == "__main__":
    main()
