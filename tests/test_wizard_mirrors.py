"""The Base System gate's repo-mirror selection: the background auto-pick populates
the selections, offline skips it, and the manual 'Choose mirrors…' modal overrides.
(Mirror selection lives on Base System — Get Online is skipped when already online.)
Headless — the latency probe (mirrors.select_mirrors) and run_blocking are stubbed."""

from __future__ import annotations

import asyncio

import urwid

from gest.core.disk import reader as disk_reader
from gest.core.install import assemble
from gest.core.portage.mirrors import MirrorSelection
from gest.tui.runtime import App, Modal
from gest.tui.screens.install import wizard as wz

_PICK = MirrorSelection(distfiles=("https://mirrors.mit.edu/gentoo-distfiles/",
                                   "https://mirror.rackspace.com/gentoo/"),
                        sync_uri="rsync://rsync.us.gentoo.org/gentoo-portage", probed=True)


def _base_step(monkeypatch, *, online=True):
    monkeypatch.setattr(wz, "check_connectivity", lambda: (online, "ok" if online else "no route"))
    monkeypatch.setattr(disk_reader, "list_block_devices", lambda: [])
    monkeypatch.setattr(wz.net_reader, "list_interfaces", lambda *a, **k: [])
    app = App()
    # Base System kicks the mirror probe from setting_rows on construction; make
    # run_async a coro-closing no-op so building the step schedules no real probe.
    monkeypatch.setattr(app, "run_async", lambda coro: coro.close())
    sel = assemble.propose("desktop")
    step = wz.BaseSystemStep(app, sel)
    app._stack.append(step)
    return app, step, sel


def _modal(app) -> Modal:
    w = app._stack[-1].top_w
    while not isinstance(w, Modal):
        w = w.original_widget
    return w


def test_probe_populates_selections(monkeypatch):
    app, step, sel = _base_step(monkeypatch)
    monkeypatch.setattr(wz.mirrors, "select_mirrors", lambda *a, **k: _PICK)

    async def _run_blocking(fn, *a):        # no real executor/loop in tests
        return fn(*a)
    monkeypatch.setattr(app, "run_blocking", _run_blocking)
    asyncio.run(step._probe_mirrors())
    assert sel.gentoo_mirrors == _PICK.distfiles
    assert sel.sync_uri == _PICK.sync_uri
    assert "mit.edu" in step._mirror_value() and "auto-picked" in step._mirror_value()


def test_ensure_skips_when_offline(monkeypatch):
    _app, step, sel = _base_step(monkeypatch, online=False)
    step._mirror_probe_started = False              # reset from any construction-time kick
    sel.gentoo_mirrors = ()
    step._ensure_mirrors()                          # offline (check_connectivity stubbed False)
    assert getattr(step, "_mirror_probe_started", False) is False
    assert sel.gentoo_mirrors == ()
    assert "default rotation" in step._mirror_value()


def test_ensure_kicks_once_when_online(monkeypatch):
    _app, step, sel = _base_step(monkeypatch)
    step._mirror_probe_started = False              # fresh state, ignore construction kick
    sel.gentoo_mirrors = ()
    calls = []
    monkeypatch.setattr(step.app, "run_async", lambda coro: calls.append(coro) or coro.close())
    step._ensure_mirrors()
    step._ensure_mirrors()                          # second call must not kick again
    assert len(calls) == 1
    assert step._mirror_probe_started is True


def test_manual_choose_overrides(monkeypatch):
    app, step, sel = _base_step(monkeypatch)
    step._choose_mirrors()
    modal = _modal(app)
    boxes = [w for w, _o in modal._pile.contents if isinstance(w, urwid.CheckBox)]
    assert len(boxes) == len(wz.mirrors.CATALOG)
    boxes[1].set_state(True)                # pick the second catalog mirror
    modal._primary()                        # Save
    assert sel.gentoo_mirrors == (wz.mirrors.CATALOG[1].distfiles,)
    assert sel.sync_uri == wz.mirrors.CATALOG[1].rsync


def test_repick_clears_and_reprobes(monkeypatch):
    _app, step, sel = _base_step(monkeypatch)
    sel.gentoo_mirrors = _PICK.distfiles
    step._mirror_probe_started = True
    monkeypatch.setattr(step.app, "run_async", lambda coro: coro.close())
    step._repick_mirrors()
    assert sel.gentoo_mirrors == ()                 # current pick cleared…
    assert step._mirror_probe_started is True        # …and the re-render immediately re-probes


def test_assemble_carries_mirrors():
    from gest.core.install.assemble import assemble_plan
    from gest.core.stage3.model import Stage3Selection
    stage3 = Stage3Selection(url="https://m/s.tar.xz", filename="s.tar.xz", size=1,
                             digests_url="https://m/s.DIGESTS", signature_url="https://m/s.asc")
    sel = assemble.propose("desktop")               # rootless → needs an admin user
    sel.disk = "sda"
    sel.users = [assemble.UserDraft(name="captain", admin=True, password="pw")]
    sel.gentoo_mirrors = _PICK.distfiles
    sel.sync_uri = _PICK.sync_uri
    plan = assemble_plan(sel, stage3)
    assert plan.gentoo_mirrors == _PICK.distfiles
    assert plan.sync_uri == _PICK.sync_uri
