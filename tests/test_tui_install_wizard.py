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


def _step(cls, sel=None):
    app = App()
    sel = sel if sel is not None else assemble.propose("desktop")
    step = cls(app, sel)
    app._stack.append(step)
    return app, step, sel


def test_rail_is_the_mainline_order():
    assert [k for k, _ in wz._RAIL] == [
        "localization", "online", "role", "disk", "base", "account", "review"]


def test_localization_advances_to_online():
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
