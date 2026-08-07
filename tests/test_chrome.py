"""Unit tests for the reusable YaST-style chrome widgets."""

from gest.tui.widgets.bracket_button import BracketButton
from gest.tui.widgets.function_bar import FunctionBar


def test_function_bar_markup_lists_all_keys():
    markup = FunctionBar([("F1", "Help"), ("F10", "Accept")])._markup()
    assert "F1" in markup and "Help" in markup
    assert "F10" in markup and "Accept" in markup
    assert "[reverse]" in markup  # keys are rendered as reversed chips


def test_bracket_button_label():
    btn = BracketButton("Run", id="run")
    assert btn.label == "Run"
    assert btn.id == "run"
