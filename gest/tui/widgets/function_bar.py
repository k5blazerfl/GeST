"""A YaST-style function-key footer: reversed Fn chips followed by labels."""

from __future__ import annotations

from textual.widgets import Static


class FunctionBar(Static):
    """Bottom bar showing function-key hints, e.g. ``F1 Help  F10 Accept``.

    Pass ``keys`` as ``[(key, label), …]``. Purely presentational — the actual
    bindings live on the screen; this just renders the legend YaST users expect.
    """

    DEFAULT_CSS = """
    FunctionBar {
        dock: bottom;
        height: 1;
        width: 100%;
        background: $panel;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self, keys: list[tuple[str, str]], **kwargs) -> None:
        self._keys = list(keys)
        super().__init__(self._markup(), **kwargs)

    def set_keys(self, keys: list[tuple[str, str]]) -> None:
        self._keys = list(keys)
        self.update(self._markup())

    def _markup(self) -> str:
        return "  ".join(f"[reverse] {key} [/reverse] {label}" for key, label in self._keys)
