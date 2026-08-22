"""The GeSI install wizard rail (urwid) — gate navigation + validation. Headless:
construct gates over an App with network/disks stubbed, then drive advance()."""

from __future__ import annotations

import pytest

from gest.core.disk import reader as disk_reader
from gest.core.install import assemble
from gest.tui.runtime import App
from gest.tui.screens.install import wizard as wz


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch):
    monkeypatch.setattr(wz, "check_connectivity", lambda: (True, "ok"))
    monkeypatch.setattr(disk_reader, "list_block_devices", lambda: [])
    monkeypatch.setattr(wz.net_reader, "list_interfaces", lambda *a, **k: [])


def _step(cls, sel=None):
    app = App()
    sel = sel if sel is not None else assemble.propose("desktop")
    step = cls(app, sel)
    app._stack.append(step)
    return app, step, sel


def test_rail_is_the_mainline_order():
    assert [k for k, _ in wz._RAIL] == [
        "localization", "online", "role", "disk", "base", "account", "review"]


def test_welcome_skips_get_online_when_already_connected():
    # background warm-up got us online → Welcome goes straight to System Role
    app, step, _ = _step(wz.LocalizationStep)
    step.advance()
    assert isinstance(app._stack[-1], wz.RoleStep)


def test_welcome_goes_to_get_online_when_offline(monkeypatch):
    monkeypatch.setattr(wz, "check_connectivity", lambda: (False, "no route"))
    app, step, _ = _step(wz.LocalizationStep)
    step.advance()
    assert isinstance(app._stack[-1], wz.OnlineStep)


def test_online_blocks_when_offline(monkeypatch):
    monkeypatch.setattr(wz, "check_connectivity", lambda: (False, "no route"))
    app, step, _ = _step(wz.OnlineStep)
    step.advance()
    assert app._stack[-1] is step                       # blocked — did not advance
    assert step.validate() is not None


def test_online_advances_when_connected():
    app, step, _ = _step(wz.OnlineStep)
    step.advance()
    assert isinstance(app._stack[-1], wz.RoleStep)


def test_role_choice_mutates_shared_selection():
    _app, step, sel = _step(wz.RoleStep, assemble.propose("desktop"))
    step._choose("server")()
    assert sel.role == "server"
    assert sel.install_desktop is False and sel.admin_model == "traditional"
    assert sel.tier2 == {"sshd", "firewall"}


def test_disk_requires_a_target():
    sel = assemble.propose("desktop")
    sel.disk = ""
    app, step, _ = _step(wz.DiskStep, sel)
    assert step.validate() is not None
    step.advance()
    assert app._stack[-1] is step                       # blocked


def test_disk_pick_applies_guided_sizes():
    _app, step, sel = _step(wz.DiskStep)
    step._on_disk("vda")
    assert sel.disk == "vda"
    assert sel.esp_size == "1G" and sel.swap_size.endswith("G")


def test_account_rootless_needs_admin_user():
    sel = assemble.propose("desktop")                   # rootless
    sel.create_user = False
    _app, step, _ = _step(wz.AccountStep, sel)
    assert step.validate() is not None
    sel.create_user = True
    sel.user_name = "captain"
    sel.user_wheel = True
    assert step.validate() is None


def test_account_traditional_needs_root_password():
    sel = assemble.propose("server")                    # traditional
    _app, step, _ = _step(wz.AccountStep, sel)
    assert step.validate() is not None
    sel.root_password = "hunter2"
    assert step.validate() is None


def test_account_advances_into_the_review_overview():
    sel = assemble.propose("server")
    sel.root_password = "x"
    sel.disk = "vda"
    app, step, _ = _step(wz.AccountStep, sel)
    step.advance()
    from gest.tui.screens.install.review import ReviewScreen
    top = app._stack[-1]
    assert isinstance(top, ReviewScreen)
    assert top.sel is sel                               # the same selection flows through


def test_make_step_review_is_the_review_gate():
    from gest.tui.screens.install.review import ReviewScreen
    scr = wz.make_step("review", App(), assemble.propose("desktop"))
    assert isinstance(scr, ReviewScreen)


def test_start_seeds_desktop_proposal():
    step = wz.start(App())
    assert isinstance(step, wz.LocalizationStep)
    assert step.sel.role == "desktop"


def test_continue_is_a_bottom_action_button_that_advances():
    app, step, _ = _step(wz.LocalizationStep)
    # Back + Continue live in a right-aligned ActionRow, not the settings list
    assert len(step._nav_row.buttons) == 2, "expected Back + Continue buttons"
    step._nav_row.focus_position = step._nav_row.button_position(1)   # Continue
    assert step._nav_row.activate_focused() is True                   # fires advance()
    assert isinstance(app._stack[-1], wz.RoleStep)                    # online → skips Get Online


def test_back_button_pops_to_previous_gate():
    app = App()
    sel = assemble.propose("desktop")
    first = wz.LocalizationStep(app, sel)
    app._stack.append(first)
    second = wz.OnlineStep(app, sel)
    app._stack.append(second)
    second._nav_row.focus_position = second._nav_row.button_position(0)  # Back
    assert second._nav_row.activate_focused() is True
    assert app._stack[-1] is first                                    # stepped back


def test_welcome_is_a_cover_page_with_gesi_ascii_logo_and_no_rail():
    app, step, _ = _step(wz.LocalizationStep)
    out = "\n".join(r.decode() for r in step.render((94, 34), focus=True).text)
    assert wz._GESI_LOGO_LINES[-1] in out             # the GESI wordmark (T→I)
    assert "-Gentoo System Installer-" in out
    assert "Welcome! Let's get started!" in out
    assert "Language / Locale" in out
    # cover page: the step-rail (other gates' titles) is NOT shown here
    assert "Get Online" not in out and "System Role" not in out
    # still advances into the rail proper (online here → System Role)
    step.advance()
    assert isinstance(app._stack[-1], wz.RoleStep)


def test_gesi_logo_differs_from_gest_only_by_the_I_bottom_bar():
    from gest.tui.screens.loading import _LOGO_LINES
    # first six rows identical to the GeST mark; only the last row gains the I's bar
    assert wz._GESI_LOGO_LINES[:6] == _LOGO_LINES[:6]
    assert wz._GESI_LOGO_LINES[6].endswith("###########")   # I bottom bar
    assert wz._GESI_LOGO_LINES[6] != _LOGO_LINES[6]


def test_welcome_exit_to_terminal_quits(monkeypatch):
    import urwid
    app = App()
    step = wz.start(app, exit_to_terminal=True)         # standalone installer root
    app._stack.append(step)
    labels = ["".join(str(t) for t in b.base_widget.get_text()[0])
              for b in step._nav_row.buttons]
    assert any("Exit to Terminal" in x for x in labels)
    # activating it raises ExitMainLoop (quit to shell), not a pop
    step._nav_row.focus_position = step._nav_row.button_position(0)
    with pytest.raises(urwid.ExitMainLoop):
        step._nav_row.activate_focused()


def test_welcome_from_menu_keeps_back(monkeypatch):
    # launched WITHOUT exit_to_terminal → first button is Back (returns to menu)
    app = App()
    step = wz.start(app)                                # default exit_to_terminal=False
    app._stack.append(step)
    labels = ["".join(str(t) for t in b.base_widget.get_text()[0])
              for b in step._nav_row.buttons]
    assert any("Back" in x for x in labels) and not any("Exit" in x for x in labels)


def test_online_no_usable_devices_blocks_with_clear_message(monkeypatch):
    monkeypatch.setattr(wz, "check_connectivity", lambda: (False, "no route"))
    monkeypatch.setattr(wz.net_reader, "list_interfaces", lambda *a, **k: [])
    _app, step, _ = _step(wz.OnlineStep)
    out = "\n".join(r.decode() for r in step.render((90, 30), focus=True).text)
    assert "No usable network devices" in out
    assert "No usable network devices" in (step.validate() or "")


def test_online_lists_devices_and_offers_wifi(monkeypatch):
    from gest.core.network.model import Interface
    monkeypatch.setattr(wz, "check_connectivity", lambda: (False, "no route"))
    monkeypatch.setattr(wz.net_reader, "list_interfaces", lambda *a, **k: [
        Interface(name="enp0s3", state="DOWN"),
        Interface(name="wlp2s0", state="DOWN"),
    ])
    _app, step, _ = _step(wz.OnlineStep)
    out = "\n".join(r.decode() for r in step.render((90, 30), focus=True).text)
    assert "enp0s3 (wired)" in out and "wlp2s0 (Wi-Fi)" in out
    assert "Set up Wi-Fi" in out          # a Wi-Fi device is present
    assert step.validate() is not None    # present but not connected → still blocks


def test_online_passes_when_connected(monkeypatch):
    from gest.core.network.model import Interface
    monkeypatch.setattr(wz.net_reader, "list_interfaces", lambda *a, **k: [
        Interface(name="enp0s3", state="UP", addresses=["192.168.1.5/24"])])
    # default stub: check_connectivity → (True, "ok")
    _app, step, _ = _step(wz.OnlineStep)
    assert step.validate() is None


def test_role_cards_nudge_hede_and_omit_admin_style():
    labels = [lbl for _k, lbl in wz.RoleStep._ROLES]
    desktop = next(lbl for lbl in labels if lbl.startswith("Desktop"))
    assert "Helm" in desktop                      # a friendly nudge toward our HeDE
    blob = " ".join(labels).lower()
    # the admin/root style is user-choosable on the Account gate, so it must NOT
    # be advertised on the role cards
    for term in ("rootless", "sudo", "doas", "root", " su"):
        assert term not in blob, f"role cards should not mention {term!r}"


def test_picker_enter_selects_the_focused_row():
    import urwid
    fired = []
    walker = urwid.SimpleFocusListWalker([wz._row("sda"), wz._row("sdb")])
    lst = wz._EnterList(walker, lambda: fired.append(walker.get_focus()[1]))
    lst.render((20, 5), focus=True)          # ListBox needs a render before keypress
    walker.set_focus(1)
    assert lst.keypress((20, 5), "enter") is None   # consumed
    assert fired == [1]                              # Enter fired select on the focused row


def test_modal_tab_cycles_focus_between_body_and_buttons():
    import urwid

    from gest.tui.runtime import Modal
    app = App()
    body = urwid.BoxAdapter(urwid.ListBox(urwid.SimpleFocusListWalker([wz._row("x")])), 3)
    m = Modal(app, "Pick", [body], [("Select", lambda: None), ("Cancel", lambda: None)])
    # pile: 0 title, 1 divider, 2 body(selectable), 3 divider, 4 buttons(selectable)
    m._pile.focus_position = 2
    m._cycle_focus(1)
    assert m._pile.focus_position == 4               # Tab → buttons
    m._cycle_focus(1)
    assert m._pile.focus_position == 2               # Tab wraps back to the list
    m._cycle_focus(-1)
    assert m._pile.focus_position == 4               # Shift-Tab → buttons


def test_welcome_shows_current_time_and_clock_row():
    _app, step, _ = _step(wz.LocalizationStep)
    out = "\n".join(r.decode() for r in step.render((92, 36), focus=True).text)
    assert "🕑" in out                       # current-time display
    assert "Clock" in out and "chrony" in out


def test_welcome_clock_local_renders():
    sel = assemble.propose("desktop")
    sel.clock = "local"
    _app, step, _ = _step(wz.LocalizationStep, sel)
    out = "\n".join(r.decode() for r in step.render((92, 36), focus=True).text)
    assert "local (no sync)" in out
