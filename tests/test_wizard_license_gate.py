"""The License gate — its own wizard step now. Relevance-aware validation (the
Libre-on-NVIDIA trap blocks here), the per-agreement full-text view+accept flow
(each agreement soft-locked into sel.accepted_licenses), and the rung-change reset.
Headless — drive the pushed modal via its buttons; control GPU auto-detection by
stubbing assemble.resolve_gpu."""

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


def _gate(monkeypatch, **selattrs):
    monkeypatch.setattr(wz, "check_connectivity", lambda: (True, "ok"))
    monkeypatch.setattr(disk_reader, "list_block_devices", lambda: [])
    monkeypatch.setattr(wz.net_reader, "list_interfaces", lambda *a, **k: [])
    app = App()
    sel = assemble.propose("desktop")
    for k, v in selattrs.items():
        setattr(sel, k, v)
    step = wz.LicenseStep(app, sel)
    app._stack.append(step)
    return app, step, sel


def _modal(app) -> Modal:
    w = app._stack[-1].top_w
    while not isinstance(w, Modal):
        w = w.original_widget
    return w


def _accept_all_required(step, sel):
    sel.accepted_licenses = {a.name for a in step._review().required}


# --- validate: acceptance + the incompatible-rung blocker -------------------

def test_validate_requires_acceptance(monkeypatch):
    _no_gpu(monkeypatch)
    _app, step, sel = _gate(monkeypatch)            # desktop → full, not yet accepted
    assert sel.licenses_accepted is False
    msg = step.validate()
    assert msg and "accept" in msg.lower()
    _accept_all_required(step, sel)
    assert step.validate() is None                  # every required agreement accepted


def test_validate_blocks_libre_on_nvidia(monkeypatch):
    _nvidia_gpu(monkeypatch)
    _app, step, sel = _gate(monkeypatch, license="libre")
    _accept_all_required(step, sel)                 # even "accepting", the rung can't cover
    msg = step.validate()
    assert msg and "NVIDIA" in msg


def test_validate_allows_libre_without_nvidia(monkeypatch):
    _no_gpu(monkeypatch)
    _app, step, sel = _gate(monkeypatch, license="libre")
    _accept_all_required(step, sel)                 # libre entails nothing to accept
    assert step.validate() is None


def test_validate_needs_every_required_agreement(monkeypatch):
    _nvidia_gpu(monkeypatch)                        # full + nvidia → firmware AND NVIDIA
    _app, step, sel = _gate(monkeypatch)
    req = step._review().required
    assert len(req) >= 2
    sel.accepted_licenses = {a.name for a in req[:-1]}   # all but one
    assert step.validate() is not None                   # still blocked
    sel.accepted_licenses = {a.name for a in req}
    assert step.validate() is None


# --- the per-agreement view+accept flow -------------------------------------

def test_open_agreement_shows_scrollable_text_and_accepts(monkeypatch):
    _nvidia_gpu(monkeypatch)
    app, step, sel = _gate(monkeypatch)
    agreement = step._review().required[0]
    assert agreement.name not in sel.accepted_licenses
    step._open_agreement(agreement)
    modal = _modal(app)
    assert any(isinstance(w, urwid.BoxAdapter) for w, _o in modal._pile.contents)  # scrollable
    modal._primary()                                # the Accept button (primary)
    assert agreement.name in sel.accepted_licenses  # soft-locked in
    assert app._stack[-1] is step                   # modal popped, back to the gate


def test_setting_rows_track_per_agreement_state(monkeypatch):
    _nvidia_gpu(monkeypatch)
    _app, step, sel = _gate(monkeypatch)
    labels = {lbl: val for lbl, val, _act in step.setting_rows()}
    assert "License policy" in labels
    a = step._review().required[0]
    assert "not yet" in labels[a.label]
    sel.accepted_licenses = {a.name}
    labels = {lbl: val for lbl, val, _act in step.setting_rows()}
    assert "✓ accepted" in labels[a.label]


def test_change_rung_resets_acceptance(monkeypatch):
    _no_gpu(monkeypatch)
    app, step, sel = _gate(monkeypatch, license="full")
    _accept_all_required(step, sel)
    step._recompute_accept()
    assert sel.licenses_accepted is True
    step._change_rung()                             # opens the rung picker on top of the gate
    top = app._stack[-1]
    picker = _modal(app)
    top.keypress(_SIZE, "up")                       # full (2) → up → up → libre (0)
    top.keypress(_SIZE, "up")
    picker.focus_buttons()
    top.keypress(_SIZE, "enter")                    # Accept the staged rung
    assert sel.license == "libre"
    assert sel.licenses_accepted is False
    assert sel.accepted_licenses == set()


def test_nvidia_planned_honours_explicit_choice(monkeypatch):
    _no_gpu(monkeypatch)                             # auto-probe would say "no nvidia"
    _app, step, _sel = _gate(monkeypatch, gpu_auto=False, nvidia_proprietary=True)
    assert step._nvidia_planned() is True            # explicit choice wins over the probe
