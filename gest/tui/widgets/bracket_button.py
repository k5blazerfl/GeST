"""A flat, single-line ``[Label]`` button in the YaST bracketed style.

Textual's default Button is a three-row box; YaST renders actions as inline
``[Run]`` / ``[Accept]`` labels, so this is a focusable Static that posts a
:class:`BracketButton.Pressed` message on Enter/Space/click.
"""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widgets import Static


class BracketButton(Static):
    can_focus = True

    DEFAULT_CSS = """
    BracketButton {
        width: auto;
        height: 1;
        padding: 0 1;
        color: $text;
    }
    BracketButton:focus { text-style: bold reverse; }
    BracketButton:hover { text-style: reverse; }
    """

    class Pressed(Message):
        def __init__(self, button: BracketButton) -> None:
            self.button = button
            super().__init__()

        @property
        def control(self) -> BracketButton:
            return self.button

    def __init__(self, label: str, *, id: str | None = None) -> None:
        self._label = label
        super().__init__(f"[{label}]", id=id)

    @property
    def label(self) -> str:
        return self._label

    def on_click(self) -> None:
        self.post_message(self.Pressed(self))

    def on_key(self, event: events.Key) -> None:
        if event.key in ("enter", "space"):
            event.stop()
            self.post_message(self.Pressed(self))
