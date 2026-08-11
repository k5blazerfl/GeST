"""Software Management preferences (urwid): user-level options for this system.

These settings belong to the software system they govern (installs, removals and
clean-ups), so they live under the Software category rather than a global bucket.
The *accept mode* — how GeST confirms applying a change (installs, removals,
updates and clean-ups): review-and-click, a countdown timer, or apply as soon as
the plan resolves — plus the countdown length used by the timer mode. Stored
per-user via :mod:`gest.core.prefs`; no backend or root involved, so every change
saves immediately.
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
        self._timer = prefs.timer_seconds()
        # Focusable items, in walker order: the mode radios, then the timer row.
        self._items: list[tuple[str, str | None]] = (
            [("mode", m) for m in self._modes] + [("timer", None)])
        self._walker = urwid.SimpleFocusListWalker([])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, boxed(self._list, title="Accept changes"),
            title="Software Preferences",
            footer_keys=[("Enter", "Select"), ("Esc", "Back")],
            help_text=(
                "How GeST confirms applying software changes — installs, removals,\n"
                "updates and clean-ups all share these settings:\n\n"
                "Click to accept   review, then F10 / Enter — no timer\n"
                "Countdown timer   auto-apply after a few seconds (Esc stops it,\n"
                "                  Enter applies now)\n"
                "As soon as ready  apply the moment the plan resolves\n\n"
                "Enter / Space selects the highlighted mode.\n"
                "On Timer length, ←/→ (or -/+) adjusts the countdown seconds.\n"
                "Every change saves at once. Esc goes back."),
        )
        self._rebuild()

    def _kind(self) -> str:
        i = self._walker.focus or 0
        return self._items[i][0] if 0 <= i < len(self._items) else "mode"

    def _footer_context(self):
        if self._kind() == "timer":
            return [("←/→", "Adjust"), ("Esc", "Back")]
        return [("Enter", "Select"), ("Esc", "Back")]

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
        unit = "second" if self._timer == 1 else "seconds"
        note = "" if self._current == prefs.TIMER else "   (Countdown timer mode)"
        rows.append(_row([
            (None, "     Timer length   "),
            ("ok", f"{self._timer} {unit}"),
            ("dim", f"   ←/→ adjust{note}"),
        ]))
        self._walker[:] = rows
        self._walker.set_focus(min(focus, len(rows) - 1))
        self.app.refresh()

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        kind, value = self._items[self._walker.focus]
        if kind == "mode":
            if key in ("enter", " "):
                self._select(value)
                return None
        elif key in ("left", "-", "h"):
            self._adjust(-1)
            return None
        elif key in ("right", "+", "l"):
            self._adjust(+1)
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

    def _adjust(self, delta: int) -> None:
        new = max(prefs.TIMER_MIN, min(prefs.TIMER_MAX, self._timer + delta))
        if new == self._timer:
            return
        try:
            prefs.set_timer_seconds(new)
        except (OSError, ValueError) as exc:
            self.app.notify(f"Could not save preference: {exc}", error=True)
            return
        self._timer = new
        self._rebuild()
