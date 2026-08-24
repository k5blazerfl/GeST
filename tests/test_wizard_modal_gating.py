"""Submenu picker modals (_choice_modal / _pick_modal): Tab cycles search→list→
buttons, and a list highlight only *stages* — the Accept button commits, Enter on
the list does not select-and-exit. Driven headlessly by feeding keys to the pushed
overlay so it exercises real focus routing."""

from __future__ import annotations

import urwid

from gest.core.install import assemble
from gest.tui.runtime import App, Modal
from gest.tui.screens.install import wizard as wz

_SIZE = (80, 24)


def _app():
    app = App()
    app._stack.append(wz.LocalizationStep(app, assemble.propose("desktop")))
    return app


def _modal(app) -> Modal:
    w = app._stack[-1].top_w            # Overlay.top_w == boxed(modal)
    while not isinstance(w, Modal):
        w = w.original_widget
    return w


def _selectable_positions(modal: Modal):
    return [i for i, (w, _o) in enumerate(modal._pile.contents) if w.selectable()]


def test_pick_modal_tab_cycles_search_list_buttons():
    app = _app()
    wz._pick_modal(app, "Timezone", ["America/New_York", "Europe/London", "UTC"],
                   "UTC", lambda v: None, lambda: None)
    modal = _modal(app)
    top = app._stack[-1]
    stops = _selectable_positions(modal)
    assert len(stops) == 3                      # search field, list, button row
    assert modal._pile.focus_position == stops[0]      # starts on the search field
    seen = [modal._pile.focus_position]
    for _ in range(3):
        top.keypress(_SIZE, "tab")
        seen.append(modal._pile.focus_position)
    assert seen == [stops[0], stops[1], stops[2], stops[0]]   # cycles + wraps
    top.keypress(_SIZE, "shift tab")
    assert modal._pile.focus_position == stops[2]            # reverses


def test_pick_modal_list_stages_accept_commits():
    app = _app()
    applied = []
    wz._pick_modal(app, "Timezone", ["America/New_York", "Europe/London", "UTC"],
                   "UTC", applied.append, lambda: None)
    top = app._stack[-1]
    top.keypress(_SIZE, "tab")          # search -> list (focus starts on current, UTC)
    top.keypress(_SIZE, "up")           # stage Europe/London
    assert applied == []                # nothing applied by navigating
    top.keypress(_SIZE, "enter")        # Enter on the list advances to Accept, no commit
    assert applied == []
    assert app._stack[-1] is top        # modal still open
    top.keypress(_SIZE, "enter")        # now on Accept -> commit the staged choice
    assert applied == ["Europe/London"]
    assert app._stack[-1] is not top    # modal closed


def test_choice_modal_gated_accept():
    app = _app()
    applied = []
    wz._choice_modal(app, "Clock", [("chrony", "Network"), ("local", "Local")],
                     "chrony", applied.append, lambda: None)
    top = app._stack[-1]
    # focus starts on the list; move to the second option and Enter (should not fire)
    top.keypress(_SIZE, "down")
    top.keypress(_SIZE, "enter")        # advances to Accept, no commit
    assert applied == []
    assert app._stack[-1] is top
    top.keypress(_SIZE, "enter")        # Accept commits the staged option
    assert applied == ["local"]
    assert app._stack[-1] is not top
