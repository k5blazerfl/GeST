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
        # The standalone installer: launch straight into the wizard as the root
        # screen. The Welcome gate's "Exit to Terminal" quits to the shell — there
        # is no GeST admin menu to fall back to in this (live-medium) context.
        from gest.tui.screens.install.wizard import start as start_wizard
        app.run(start_wizard(app, exit_to_terminal=True))
    else:
        app.run(MenuScreen(app, installer=False))


if __name__ == "__main__":
    main()
