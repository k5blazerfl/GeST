"""Shared fullscreen loading screen: GeST logo, a step list, phase line + bar.

Long-running module startups — opening Package Management, computing a System
Update — show this instead of a blank pane: the ASCII logo, a subtitle, a step
list with per-step glyphs, a phase line, and a progress bar. Subclasses set the
title / subtitle / help, supply the steps, and implement ``_run()`` to do the
work and hand off to the ready screen. The optional ``_sub_rows`` hook renders
extra indented rows under a step (Software's per-repo refresh list).
"""

from __future__ import annotations

import urwid

from gest.tui.runtime import App, Screen, boxed

# Step status → glyph / attr.
_STEP_GLYPH = {"pending": "·", "active": "▸", "done": "✓",
               "skipped": "⊘", "failed": "✗"}
_STEP_ATTR = {"pending": "dim", "active": "field", "done": "ok",
              "skipped": "dim", "failed": "error"}

# GeST ASCII logo (from Art/ascii-logo.txt) — top three lines in Gentoo blue,
# the bottom four in Gentoo purple.
_LOGO_LINES = [
    "      ::::::::  :::::::::: :::::::: :::::::::::",
    "    :+:    :+: :+:       :+:    :+:    :+:",
    "   +:+        +:+       +:+           +:+",
    "  :#:        +#++:++#  +#++:++#++    +#+",
    " +#+   +#+# +#+              +#+    +#+",
    "#+#    #+# #+#       #+#    #+#    #+#",
    "########  ########## ########     ###",
]
_LOGO_W = max(len(line) for line in _LOGO_LINES)
_LOGO_MARKUP = [
    ("box_title", "\n".join(_LOGO_LINES[:3]) + "\n"),   # top 3: Gentoo blue
    ("title", "\n".join(_LOGO_LINES[3:])),              # bottom 4: Gentoo purple
]


class LoadingScreen(Screen):
    def __init__(self, app: App, steps: list[dict], *, title: str,
                 subtitle: str, help_text: str) -> None:
        self._steps = steps
        self._steps_text = urwid.Text("")
        self._phase = urwid.Text(("dim", " Starting …"))
        self._bar = urwid.ProgressBar("pb_normal", "pb_complete", 0, 1)

        logo = urwid.Padding(
            urwid.Text(_LOGO_MARKUP, wrap="clip"), align="center", width=_LOGO_W)
        panel = boxed(
            urwid.Pile([
                ("pack", urwid.Divider(" ")),      # one line of top spacing
                ("pack", logo),
                ("pack", urwid.Divider(" ")),
                ("pack", urwid.Text(("dim", subtitle), align="center")),
                ("pack", urwid.Divider(" ")),
                ("pack", self._steps_text),
                ("pack", urwid.Divider(" ")),
                ("pack", self._bar),
                ("pack", urwid.AttrMap(self._phase, "field")),
            ]),
            title=title)
        body = urwid.Filler(
            urwid.Padding(panel, align="center", width=("relative", 62),
                          min_width=_LOGO_W + 6),
            valign="middle", height="pack")
        super().__init__(app, body, title=title,
                         footer_keys=[("Esc", "Cancel")], help_text=help_text)
        self._render()
        app.run_async(self._run())

    # -- rendering ----------------------------------------------------------

    def _render(self) -> None:
        markup: list = []
        for st in self._steps:
            glyph = _STEP_GLYPH[st["status"]]
            line = f"  {glyph}  {st['label']}"
            if st["detail"]:
                line += f"   ({st['detail']})"
            markup.append((_STEP_ATTR[st["status"]], line + "\n"))
            markup.extend(self._sub_rows(st))
        self._steps_text.set_text(markup)
        self.app.refresh()

    def _sub_rows(self, step: dict) -> list:
        """Extra indented rows to render under ``step`` (default: none)."""
        return []

    def _set_step(self, key: str, status: str, detail: str = "") -> None:
        for st in self._steps:
            if st["key"] == key:
                st["status"] = status
                if detail:
                    st["detail"] = detail
        self._render()

    def _set_phase(self, text: str, attr: str = "field") -> None:
        self._phase.set_text((attr, f" {text}"))
        self.app.refresh()

    # -- work ---------------------------------------------------------------

    async def _run(self) -> None:            # subclasses do the work + hand off
        raise NotImplementedError

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()                   # cancel startup → back to the menu
            return None
        return key
