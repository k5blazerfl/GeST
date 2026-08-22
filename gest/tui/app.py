"""GeST TUI entry point (`gest`).

A urwid frontend over the frontend-agnostic ``gest.core`` modules. Run in a
real terminal.
"""

from __future__ import annotations

import argparse
import sys

from gest.tui.runtime import App
from gest.tui.screens.menu import MenuScreen


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gest",
        description="GeST — a YaST-style Gentoo system tool (TUI).")
    parser.add_argument(
        "--install", action="store_true",
        help="show the 'Install Gentoo' installer (the live-CD environment runs "
             "this); installing needs root.")
    args = parser.parse_args()

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.stderr.write(
            "gest: no interactive terminal detected — run it in a real terminal.\n"
        )
        raise SystemExit(1)
    app = App()
    if args.install:
        # Launch straight into the install wizard (first gate). The admin menu
        # (with the installer category) sits beneath it as an escape hatch, so Esc
        # from the wizard drops to the menu rather than exiting.
        from gest.tui.screens.install.wizard import start as start_wizard
        app.push(MenuScreen(app, installer=True))
        app.run(start_wizard(app))
    else:
        app.run(MenuScreen(app, installer=False))


if __name__ == "__main__":
    main()
