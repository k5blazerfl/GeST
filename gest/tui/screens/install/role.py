"""System Role — the wizard's first gate.

Instead of dropping the user into a wall of blank settings, ask one question:
what is this machine for? The chosen role proposes a coherent whole
(``assemble.propose``) — build strategy, GPU policy, license rung, admin model,
day-2 services, Features — and hands that pre-filled selection to the settings
overview, where every value is a real default the user can still change.
"""

from __future__ import annotations

import urwid

from gest.core.install import assemble
from gest.tui.runtime import App, NavPile, Screen, boxed

# (key, title, one-line description). Order = display order; Desktop leads and is
# the recommended default for the refugee-facing audience.
_ROLES: tuple[tuple[str, str, str], ...] = (
    ("desktop", "Desktop (HeDE)",
     "Full graphical Helm desktop. Rootless admin (sudo), everything licensed. "
     "Recommended."),
    ("server", "Server",
     "Headless. SSH + firewall enabled, root + su, redistributable licenses."),
    ("minimal", "Minimal",
     "Base Gentoo, compiled from source. No desktop, no extras."),
    ("custom", "Custom",
     "Start from the Desktop defaults and configure every option yourself."),
)


def _role_row(title: str, desc: str) -> urwid.Widget:
    """A selectable two-line card: bold title over a wrapped description."""
    body = urwid.Pile([
        urwid.Text(("title", title)),
        urwid.Text(("dim", desc)),
        urwid.Divider(),
    ])
    # SelectableIcon makes the whole card focusable/Enter-able; the icon column 0
    # sits on the title line. Wrap in AttrMap so focus highlights the whole card.
    return urwid.AttrMap(_Selectable(body), None, focus_map="focus")


class _Selectable(urwid.WidgetWrap):
    """Make a composite (Pile) widget focusable so Enter reaches the screen."""

    _selectable = True

    def keypress(self, size, key):   # let the ListBox/Screen handle keys
        return key


class RoleScreen(Screen):
    """Pick what the machine is for; propose a selection; open the overview."""

    def __init__(self, app: App) -> None:
        rows = [urwid.Text(("hint",
                            " What is this machine for? Pick a role — you can change "
                            "any setting afterwards.")),
                urwid.Divider()]
        for _key, title, desc in _ROLES:
            rows.append(_role_row(title, desc))
        self._walker = urwid.SimpleFocusListWalker(rows)
        self._list = urwid.ListBox(self._walker)
        # Focus the first role card (index 2: after the hint + divider).
        self._first_role_pos = 2
        self._walker.set_focus(self._first_role_pos)
        pile = NavPile([boxed(self._list, title="System Role")])
        super().__init__(
            app, pile, title="Install Gentoo — System Role",
            footer_keys=[("Enter", "Choose"), ("Esc", "Back")],
            help_text=(
                "Choose a role. Each proposes a coherent set of defaults:\n\n"
                "  Desktop  full HeDE desktop, rootless sudo, all licenses\n"
                "  Server   headless, sshd + firewall, root + su\n"
                "  Minimal  base Gentoo from source, no desktop\n"
                "  Custom   the Desktop baseline with everything editable\n\n"
                "Nothing is applied here — the next screen lets you review and edit\n"
                "every setting before anything touches a disk."
            ),
        )

    def _focused_role(self) -> str | None:
        pos = self._walker.get_focus()[1]
        idx = pos - self._first_role_pos
        if 0 <= idx < len(_ROLES):
            return _ROLES[idx][0]
        return None

    def _move(self, delta: int) -> None:
        """Move the card focus within the role rows (they're all on screen, so we
        drive the walker directly rather than depend on ListBox scroll state)."""
        pos = self._walker.get_focus()[1]
        low, high = self._first_role_pos, self._first_role_pos + len(_ROLES) - 1
        self._walker.set_focus(min(high, max(low, pos + delta)))

    def handle_key(self, key):
        if key in ("up", "down"):
            self._move(1 if key == "down" else -1)
            return None
        if key == "enter":
            role = self._focused_role()
            if role is None:
                return None
            selections = assemble.propose(role)
            # Import here to avoid a cycle (installer imports runtime; role is a peer).
            from gest.tui.screens.installer import InstallOverviewScreen
            self.app.push(InstallOverviewScreen(self.app, selections))
            return None
        return key
