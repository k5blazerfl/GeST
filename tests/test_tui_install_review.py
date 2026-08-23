"""The wizard Review gate (urwid): grouped readout, blockers, jump-back, install
gating. Headless — network/disks stubbed."""

from __future__ import annotations

import pytest

from gest.core.install import assemble
from gest.tui.runtime import App
from gest.tui.screens.install import review as rv
from gest.tui.screens.install import wizard as wz

_SIZE = (100, 44)


def _render(w) -> str:
    return "\n".join(row.decode() for row in w.render(_SIZE, focus=True).text)


@pytest.fixture(autouse=True)
def _online(monkeypatch):
    monkeypatch.setattr(rv, "check_connectivity", lambda: (True, "ok"))


def _ready_desktop():
    sel = assemble.propose("desktop")            # rootless
    sel.disk = "vda"
    # rootless needs an admin user with a password
    sel.users = [assemble.UserDraft(name="captain", admin=True, password="hunter2")]
    return sel


def _review(sel):
    app = App()
    scr = rv.ReviewScreen(app, sel)
    app._stack.append(scr)
    return app, scr


def test_review_renders_grouped_readout():
    _app, scr = _review(_ready_desktop())
    out = _render(scr)
    for group in ("Localization", "System", "Disk", "Base System", "Account"):
        assert group in out
    assert "Install" in out


def test_rootless_root_reads_disabled():
    _app, scr = _review(_ready_desktop())            # desktop = rootless, root locked
    out = _render(scr)
    assert "Root" in out and "disabled" in out
    assert "(set)" not in out and "(not set)" not in out   # no password flags


def test_traditional_root_reads_enabled():
    sel = assemble.propose("server")                 # traditional → root has a password
    sel.disk = "vda"
    _app, scr = _review(sel)
    assert "enabled" in _render(scr)


def test_review_shows_users_as_a_roster():
    sel = _ready_desktop()
    sel.users.append(assemble.UserDraft(name="guest", admin=False, password="g"))
    out = _render(_review(sel)[1])
    assert "captain" in out and "(admin)" in out and "guest" in out
    assert "password set" not in out                 # password flags gone


def test_ready_selection_has_no_blockers_and_offers_install():
    _app, scr = _review(_ready_desktop())
    assert scr._blockers() == []
    # Install is a bottom-right action button (GeST ActionRow), always present.
    assert any("Install" in "".join(
        str(t) for t in btn.base_widget.get_text()[0]) for btn in scr._install_row.buttons)


def test_missing_disk_blocks_and_install_is_refused():
    sel = _ready_desktop()
    sel.disk = ""
    _app, scr = _review(sel)
    assert "a target disk" in scr._blockers()
    assert "Install disabled" in _render(scr)       # blocker banner shown


def test_rootless_without_user_blocks():
    sel = assemble.propose("desktop")              # rootless, no user yet
    sel.disk = "vda"
    _app, scr = _review(sel)
    assert "an administrator account" in scr._blockers()


def test_offline_blocks(monkeypatch):
    monkeypatch.setattr(rv, "check_connectivity", lambda: (False, "no route"))
    _app, scr = _review(_ready_desktop())
    assert "a network connection" in scr._blockers()


def test_derived_rows_are_not_jump_targets():
    _app, scr = _review(_ready_desktop())
    # Stage3/Profile are derived → present but with no gate target
    out = _render(scr)
    assert "derived" in out


def test_changed_marker_when_off_proposal():
    sel = _ready_desktop()
    sel.license = "libre"                            # desktop proposes "full"
    _app, scr = _review(sel)
    assert "•changed" in _render(scr)


def test_enter_on_a_row_jumps_to_owning_gate():
    _app, scr = _review(_ready_desktop())
    # focus the first selectable (a Localization row → gate "localization")
    stops = scr._stops()
    scr._walker.set_focus(stops[0])
    scr.handle_key("enter")
    top = _app._stack[-1]
    assert isinstance(top, wz.LocalizationStep)
    # editing there and Continue returns to a fresh Review
    top.advance()
    assert isinstance(_app._stack[-1], rv.ReviewScreen)


def test_install_blocked_notifies(monkeypatch):
    sel = _ready_desktop()
    sel.disk = ""
    app, scr = _review(sel)
    notes = []
    monkeypatch.setattr(app, "notify", lambda msg, error=False: notes.append((msg, error)))
    scr._install()
    assert notes and notes[-1][1] is True           # error notification, no launch
