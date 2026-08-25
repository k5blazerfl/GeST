"""The Base System gate's pre-flight license gate: relevance-aware validation
(the Libre-on-NVIDIA trap blocks here), the explicit view+accept modal, and the
rung-change reset. Headless — drive the pushed modal via keypress/primary, and
control GPU auto-detection by stubbing assemble.resolve_gpu."""

from __future__ import annotations

import urwid

from gest.core.disk import reader as disk_reader
from gest.core.install import assemble
from gest.core.install.plan import GpuSpec
from gest.tui.runtime import App, Modal
from gest.tui.screens.install import wizard as wz

_SIZE = (80, 24)


def _no_gpu(monkeypatch):
    monkeypatch.setattr(wz.assemble, "resolve_gpu", lambda *a, **k: GpuSpec())


def _nvidia_gpu(monkeypatch):
    monkeypatch.setattr(wz.assemble, "resolve_gpu",
                        lambda *a, **k: GpuSpec(video_cards=("nvidia",), nvidia_proprietary=True))


def _base(monkeypatch, **selattrs):
    monkeypatch.setattr(wz, "check_connectivity", lambda: (True, "ok"))
    monkeypatch.setattr(disk_reader, "list_block_devices", lambda: [])
    monkeypatch.setattr(wz.net_reader, "list_interfaces", lambda *a, **k: [])
    app = App()
    sel = assemble.propose("desktop")
    for k, v in selattrs.items():
        setattr(sel, k, v)
    step = wz.BaseSystemStep(app, sel)
    app._stack.append(step)
    return app, step, sel


def _modal(app) -> Modal:
    w = app._stack[-1].top_w
    while not isinstance(w, Modal):
        w = w.original_widget
    return w


def _checkbox(modal):
    for w, _o in modal._pile.contents:
        if isinstance(w, urwid.CheckBox):
            return w
    return None


# --- validate: acceptance + the incompatible-rung blocker -------------------

def test_validate_requires_acceptance(monkeypatch):
    _no_gpu(monkeypatch)
    _app, step, sel = _base(monkeypatch)            # desktop → full, not yet accepted
    assert sel.licenses_accepted is False
    msg = step.validate()
    assert msg and "accept" in msg.lower()
    sel.licenses_accepted = True
    assert step.validate() is None                  # full + no nvidia → clean once accepted


def test_validate_blocks_libre_on_nvidia(monkeypatch):
    _nvidia_gpu(monkeypatch)
    _app, step, sel = _base(monkeypatch, license="libre")
    sel.licenses_accepted = True                    # even having "accepted", the rung can't cover
    msg = step.validate()
    assert msg and "NVIDIA" in msg


def test_validate_allows_libre_without_nvidia(monkeypatch):
    _no_gpu(monkeypatch)
    _app, step, sel = _base(monkeypatch, license="libre")
    sel.licenses_accepted = True
    assert step.validate() is None                  # firmware-free libre is a valid choice


# --- the view+accept modal --------------------------------------------------

def test_accept_flow_sets_accepted(monkeypatch):
    _no_gpu(monkeypatch)
    app, step, sel = _base(monkeypatch)
    step._open_license_gate()
    modal = _modal(app)
    cb = _checkbox(modal)
    assert cb is not None and cb.state is False
    cb.set_state(True)
    modal._primary()                                # the Accept button callback
    assert sel.licenses_accepted is True
    assert not isinstance(app._stack[-1], type(modal))   # modal popped, back to the gate


def test_accept_refused_without_ticking(monkeypatch):
    _no_gpu(monkeypatch)
    app, step, sel = _base(monkeypatch)
    monkeypatch.setattr(app, "notify", lambda *a, **k: None)
    step._open_license_gate()
    modal = _modal(app)
    modal._primary()                                # box unticked → refuse
    assert sel.licenses_accepted is False
    assert app._stack[-1] is not step               # modal still up


def test_accept_refused_through_a_blocker(monkeypatch):
    _nvidia_gpu(monkeypatch)
    app, step, sel = _base(monkeypatch, license="libre")
    monkeypatch.setattr(app, "notify", lambda *a, **k: None)
    step._open_license_gate()
    modal = _modal(app)
    cb = _checkbox(modal)
    if cb is not None:
        cb.set_state(True)
    modal._primary()
    assert sel.licenses_accepted is False           # a blocker can't be accepted through


def test_change_rung_resets_acceptance(monkeypatch):
    _no_gpu(monkeypatch)
    app, step, sel = _base(monkeypatch, license="full", licenses_accepted=True)
    step._open_license_gate()
    step._change_rung()                             # pops the gate, opens the rung picker
    # stage a different rung (Libre) and accept it → acceptance is reset
    top = app._stack[-1]
    picker = _modal(app)
    picker._pile.focus_position = next(
        i for i, (w, _o) in enumerate(picker._pile.contents) if w.selectable())
    # move the list focus to the first rung (Libre) and commit via the buttons
    top.keypress(_SIZE, "up")
    top.keypress(_SIZE, "up")
    picker.focus_buttons()
    top.keypress(_SIZE, "enter")                    # Accept the staged rung
    assert sel.license == "libre"
    assert sel.licenses_accepted is False


def test_view_license_opens_scrollable_text(monkeypatch):
    _no_gpu(monkeypatch)
    app, step, _sel = _base(monkeypatch)
    review = step._current_review()
    step._view_license(review.entails[0])
    modal = _modal(app)
    assert any(isinstance(w, urwid.BoxAdapter) for w, _o in modal._pile.contents)


# --- row value / nvidia relevance ------------------------------------------

def test_license_row_value_reflects_state(monkeypatch):
    _no_gpu(monkeypatch)
    _app, step, sel = _base(monkeypatch)
    assert "not yet accepted" in step._license_row_value()
    sel.licenses_accepted = True
    assert "accepted" in step._license_row_value()
    sel.license = "libre"
    sel.nvidia_proprietary, sel.gpu_auto = True, False   # explicit NVIDIA, no auto-probe
    assert "incompatible" in step._license_row_value()


def test_nvidia_planned_honours_explicit_choice(monkeypatch):
    _no_gpu(monkeypatch)                              # auto-probe would say "no nvidia"
    _app, step, _sel = _base(monkeypatch, gpu_auto=False, nvidia_proprietary=True)
    assert step._nvidia_planned() is True             # explicit choice wins over the probe
