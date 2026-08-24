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


def _list_row_texts(modal):
    for w, _o in modal._pile.contents:
        if isinstance(w, urwid.BoxAdapter):
            return [r.original_widget.text for r in w.original_widget.body]
    return []


def test_choice_marker_follows_focus_even_with_no_current():
    # Regression: in the Target-disk picker (no prior selection), highlighting a
    # disk showed nothing until Accept+reopen. The ◉ now follows the focus, so the
    # staged row is always marked — including the first row on open.
    app = _app()
    wz._choice_modal(app, "Target disk",
                     [("sda", "sda"), ("sdb", "sdb"), ("nvme0n1", "nvme0n1")], "",
                     lambda v: None, lambda: None)
    top = app._stack[-1]
    rows = _list_row_texts(_modal(app))
    assert rows[0].startswith("◉ ") and rows[1].startswith("○ ")   # staged on open
    top.keypress(_SIZE, "down")
    rows = _list_row_texts(_modal(app))
    assert rows[1].startswith("◉ ") and rows[0].startswith("○ ")   # moved with focus
    assert sum(t.startswith("◉") for t in rows) == 1               # exactly one


def test_pick_marker_follows_focus(monkeypatch):
    from gest.core.system import locale as loc
    monkeypatch.setattr(loc, "list_locales", lambda: ["C", "C.utf8", "en_US.utf8"])
    app = _app()
    app._stack[-1].sel.locale = "C.UTF-8"
    app._stack[-1]._edit_locale()
    top = app._stack[-1]
    rows = _list_row_texts(_modal(app))
    assert [t for t in rows if t.startswith("▸ ")] == ["▸ C.utf8"]   # current, on open
    top.keypress(_SIZE, "tab")        # search → list
    top.keypress(_SIZE, "down")       # stage the next row
    rows = _list_row_texts(_modal(app))
    assert [t for t in rows if t.startswith("▸ ")] == ["▸ en_US.utf8"]


def test_root_password_mismatch_warns_inside_the_modal():
    # A failed password check must show IN the modal — app.notify lands on the
    # status line the modal hides, so the old code gave no visible feedback.
    app = App()
    step = wz.AccountStep(app, assemble.propose("desktop"))
    app._stack.append(step)
    step.sel.admin_model = "traditional"          # root has a password
    step._edit_rootpw()
    top = app._stack[-1]
    m = _modal(app)
    pw, pw2, warn = (m._pile.contents[2][0], m._pile.contents[3][0],
                     m._pile.contents[5][0])
    pw.set_edit_text("secret1")
    pw2.set_edit_text("secret2")                  # mismatch
    m.focus_buttons()
    top.keypress(_SIZE, "enter")                  # Save
    assert "do not match" in warn.get_text()[0].lower()   # warning shown in-modal
    assert app._stack[-1] is top                          # modal stays open
    assert step.sel.root_password == ""                   # not applied
    pw2.set_edit_text("secret1")                  # fix it
    top.keypress(_SIZE, "enter")
    assert app._stack[-1] is not top and step.sel.root_password == "secret1"


def test_disk_picker_has_a_none_row_marked_when_unset(monkeypatch):
    # With no disk chosen, the follow-focus ◉ would otherwise land on the first real
    # disk and read as pre-selected. A "None" row at the top holds the marker until
    # you pick a disk, so nothing looks set when nothing is.
    from types import SimpleNamespace as NS

    from gest.core.disk import reader as dr
    disks = [NS(name="sda", size="238G", type="disk"),
             NS(name="sdb", size="1T", type="disk")]
    monkeypatch.setattr(dr, "list_block_devices", lambda: disks)
    app = App()
    step = wz.DiskStep(app, assemble.propose("desktop"))
    app._stack.append(step)
    assert step.sel.disk == ""                      # nothing selected on entry
    step._pick_disk(disks)
    rows = _list_row_texts(_modal(app))
    assert rows[0].startswith("◉ None")             # marker on None, not a disk
    assert not any(r.startswith("◉ sd") for r in rows)


def test_locale_picker_marks_the_current_value(monkeypatch):
    # Regression: the Language/Locale submenu showed no selection because sel.locale
    # ("C.UTF-8") never string-matched `locale -a`'s "C.utf8". _edit_locale now
    # resolves the notation, so the current row carries the ▸ marker.
    from gest.core.system import locale as loc
    monkeypatch.setattr(loc, "list_locales", lambda: ["C", "C.utf8", "POSIX", "en_US.utf8"])
    app = _app()
    step = app._stack[-1]
    step.sel.locale = "C.UTF-8"
    step._edit_locale()
    modal = _modal(app)
    # find the listbox (last selectable pile row) and read its rows' text
    listbox = modal._pile.contents[-3][0].original_widget      # BoxAdapter → ListBox
    texts = [w.original_widget.text for w in listbox.body]
    assert any(t.startswith("▸ C.utf8") for t in texts)        # current is marked
    assert sum(t.startswith("▸") for t in texts) == 1          # exactly one


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
