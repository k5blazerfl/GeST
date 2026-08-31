"""The License gate — now a sub-gate FLOW: the rung pick (LicenseStep), then one
full-text agreement sub-gate per license the rung entails (LicenseAgreementStep),
run straight through. Tests the relevance-aware rung blocker (the Libre-on-NVIDIA
trap), the flow (Continue pushes the agreement sub-gates; Accept records consent and
advances), the always-visible consent line, and the rung-change reset. Headless."""

from __future__ import annotations

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


# --- the rung blocker (relevance-aware); acceptance is NOT required here ------

def test_policy_validate_ok_without_acceptance(monkeypatch):
    # The policy sub-gate no longer requires acceptance — that's collected downstream
    # in the agreement sub-gates. A compatible rung validates immediately.
    _no_gpu(monkeypatch)
    _app, step, sel = _gate(monkeypatch)             # desktop → full, compatible
    assert sel.licenses_accepted is False
    assert step.validate() is None


def test_policy_validate_blocks_libre_on_nvidia(monkeypatch):
    _nvidia_gpu(monkeypatch)
    _app, step, _sel = _gate(monkeypatch, license="libre")
    msg = step.validate()
    assert msg and "NVIDIA" in msg


def test_policy_validate_allows_libre_without_nvidia(monkeypatch):
    _no_gpu(monkeypatch)
    _app, step, _sel = _gate(monkeypatch, license="libre")
    assert step.validate() is None


# --- the sub-gate flow -------------------------------------------------------

def test_continue_pushes_agreement_subgates(monkeypatch):
    _nvidia_gpu(monkeypatch)                          # full + nvidia → firmware AND NVIDIA
    app, step, sel = _gate(monkeypatch)
    req = step._review().required
    assert len(req) >= 2
    step.advance()                                    # Continue from the rung pick
    sub = app._stack[-1]
    assert isinstance(sub, wz.LicenseAgreementStep)
    assert sub._agreement.name == req[0].name and sub._index == 0
    assert sel.licenses_accepted is False             # nothing accepted yet


def test_accept_walks_every_agreement_then_advances(monkeypatch):
    _nvidia_gpu(monkeypatch)
    app, step, sel = _gate(monkeypatch)
    req = step._review().required
    step.advance()
    seen = []
    while isinstance(app._stack[-1], wz.LicenseAgreementStep):
        sub = app._stack[-1]
        seen.append(sub._agreement.name)
        sub.advance()                                 # "Accept"
        assert sub._agreement.name in sel.accepted_licenses
    assert set(seen) == {a.name for a in req}         # ran through every applicable license
    assert sel.licenses_accepted is True              # all required accepted
    assert app._stack[-1].step_key == "account"       # flowed on to Your Account


def test_libre_flows_straight_through(monkeypatch):
    _no_gpu(monkeypatch)
    app, step, sel = _gate(monkeypatch, license="libre")   # entails nothing
    step.advance()
    assert not isinstance(app._stack[-1], wz.LicenseAgreementStep)  # no agreement sub-gate
    assert sel.licenses_accepted is True
    assert app._stack[-1].step_key == "account"


def test_agreement_view_shows_the_consent_line(monkeypatch):
    _nvidia_gpu(monkeypatch)
    app, step, sel = _gate(monkeypatch)
    sub = wz.LicenseAgreementStep(app, sel, agreements=step._review().required, index=0)
    app._stack.append(sub)
    out = "\n".join(r.decode() for r in sub.render((96, 30), focus=True).text)
    assert "By clicking Accept, you are agreeing to the terms listed above." in out
    assert sub.continue_label == "Accept"


# --- rung change resets acceptance -------------------------------------------

def test_change_rung_resets_acceptance(monkeypatch):
    _no_gpu(monkeypatch)
    app, step, sel = _gate(monkeypatch, license="full")
    sel.accepted_licenses = {a.name for a in step._review().required}
    sel.licenses_accepted = True
    step._change_rung()                               # opens the rung picker on the gate
    top = app._stack[-1]
    picker = _modal(app)
    top.keypress(_SIZE, "up")                         # full (2) → up → up → libre (0)
    top.keypress(_SIZE, "up")
    picker.focus_buttons()
    top.keypress(_SIZE, "enter")                      # Accept the staged rung
    assert sel.license == "libre"
    assert sel.licenses_accepted is False
    assert sel.accepted_licenses == set()


def test_nvidia_planned_honours_explicit_choice(monkeypatch):
    _no_gpu(monkeypatch)                              # auto-probe would say "no nvidia"
    _app, step, _sel = _gate(monkeypatch, gpu_auto=False, nvidia_proprietary=True)
    assert step._nvidia_planned() is True             # explicit choice wins over the probe
