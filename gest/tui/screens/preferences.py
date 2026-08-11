"""GeST preferences (urwid): user-level UI options.

Currently just the *accept mode* — how GeST confirms applying software changes
(install / remove / clean up): review-and-click, a countdown timer, or apply as
soon as the plan resolves. Stored per-user via :mod:`gest.core.prefs`; no
backend or root involved, so selecting a mode saves immediately.
"""

from __future__ import annotations

import urwid

from gest.core import prefs
from gest.tui.runtime import App, Screen, boxed


def _row(markup) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(markup, 0), None, focus_map="focus")


class PreferencesScreen(Screen):
    def __init__(self, app: App) -> None:
        self._modes = list(prefs.ACCEPT_MODES)
        self._current = prefs.accept_mode()
        self._walker = urwid.SimpleFocusListWalker([])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, boxed(self._list, title="Accept changes"),
            title="Preferences",
            footer_keys=[("Enter", "Select"), ("Esc", "Back")],
            help_text=(
                "How GeST confirms applying software changes — installs, removals\n"
                "and clean-ups all share this setting:\n\n"
                "Click to accept   review, then F10 / Enter — no timer\n"
                "Countdown timer   auto-apply after a few seconds (Esc stops it,\n"
                "                  Enter applies now)\n"
                "As soon as ready  apply the moment the plan resolves\n\n"
                "Enter / Space selects the highlighted mode (saved at once).\n"
                "Esc goes back."),
        )
        self._rebuild()

    def _rebuild(self) -> None:
        focus = self._walker.focus or 0
        rows = []
        for mode in self._modes:
            label, desc = prefs.ACCEPT_LABELS[mode]
            selected = mode == self._current
            rows.append(_row([
                ("ok" if selected else "dim", f" {'(•)' if selected else '( )'} "),
                (None, f"{label:<18}"),
                ("dim", f"  {desc}"),
            ]))
        self._walker[:] = rows
        self._walker.set_focus(min(focus, len(rows) - 1))
        self.app.refresh()

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key in ("enter", " "):
            self._select(self._modes[self._walker.focus])
            return None
        return key

    def _select(self, mode: str) -> None:
        if mode == self._current:
            return
        try:
            prefs.set_accept_mode(mode)
        except (OSError, ValueError) as exc:
            self.app.notify(f"Could not save preference: {exc}", error=True)
            return
        self._current = mode
        self._rebuild()
        self.app.notify(f"Accept mode: {prefs.ACCEPT_LABELS[mode][0]}")
