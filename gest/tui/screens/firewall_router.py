"""Route the single "Firewall" menu entry to the live backend.

GeST ships two firewall modules — the nftables :class:`FirewallScreen` and the
firewalld :class:`FirewalldScreen` — but the menu shows one entry. This detects
which backend is actually running and opens it; when both look live, or neither
is present, it puts up a small chooser so the user picks (and, for "none", how
to install one). Both underlying screens stay reachable — nothing is removed.
"""

from __future__ import annotations

import urwid

from gest.core import firewall_detect
from gest.tui.runtime import App, Modal
from gest.tui.screens.firewall import FirewallScreen
from gest.tui.screens.firewalld import FirewalldScreen


def open_firewall(app: App) -> None:
    """Detect the live firewall backend and open it (or a chooser)."""
    status = firewall_detect.detect()
    active = status.active
    if active == "firewalld":
        app.push(FirewalldScreen(app))
    elif active == "nftables":
        app.push(FirewallScreen(app))
    else:  # "both" or "none": let the user choose
        _chooser(app, status)


def _chooser(app: App, status: firewall_detect.FirewallStatus) -> None:
    def open_firewalld():
        app.pop()
        app.push(FirewalldScreen(app))

    def open_nftables():
        app.pop()
        app.push(FirewallScreen(app))

    if status.active == "both":
        rows = [urwid.Text(("hint", " Both firewalld and a GeST-managed nftables "
                                    "ruleset look active. Choose which to manage:"))]
    else:  # "none"
        rows = [
            urwid.Text(("error", " No running firewall was detected.")),
            urwid.Divider(),
            urwid.Text(("hint", " Install one, then re-open this module:")),
            urwid.Text(("hint", "   emerge net-firewall/firewalld")),
            urwid.Text(("hint", "   emerge net-firewall/nftables")),
            urwid.Divider(),
            urwid.Text("You can still open either module below."),
        ]
    modal = Modal(
        app, "Firewall", rows,
        [("firewalld", open_firewalld), ("nftables", open_nftables),
         ("Cancel", app.pop)],
    )
    app.push_modal(modal, width=("relative", 68), height=("relative", 52))
