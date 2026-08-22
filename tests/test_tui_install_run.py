"""The branded install-run screen (InstallRunScreen): phase status machine,
the step-index + emerge (N of M) progress bar, and the failure marking. Headless
— we stub App.run_async so the real _run() (network/disks) never launches."""

from __future__ import annotations

import pytest

from gest.core.install import assemble
from gest.core.install.plan import Phase
from gest.tui.runtime import App
from gest.tui.screens import installer as inst

_SIZE = (100, 44)


@pytest.fixture
def screen(monkeypatch):
    # Don't launch the real install coroutine or leave it un-awaited.
    monkeypatch.setattr(App, "run_async", lambda self, coro: coro.close())
    app = App()
    scr = inst.InstallRunScreen(app, assemble.propose("desktop"))
    app._stack.append(scr)
    # a plausible 10-step plan spanning three phases
    scr._labels = [f"s{i}" for i in range(10)]
    scr._step_phases = (
        [Phase.PREPARE_DISK] * 3 + [Phase.BASE_SYSTEM] * 4 + [Phase.KERNEL_BOOT] * 3
    )
    scr._total_steps = 10
    return scr


def _render(w) -> str:
    return "\n".join(r.decode() for r in w.render(_SIZE, focus=True).text)


def test_phase_status_progression(screen):
    screen._active_phase = Phase.KERNEL_BOOT
    assert screen._phase_status(Phase.PREPARE_DISK) == "done"
    assert screen._phase_status(Phase.BASE_SYSTEM) == "done"
    assert screen._phase_status(Phase.KERNEL_BOOT) == "active"
    assert screen._phase_status(Phase.USERS_NETWORK) == "pending"
    assert screen._phase_status(Phase.FINISH) == "pending"


def test_on_step_sets_active_phase_and_bar(screen):
    screen._on_step(3)                       # into BASE_SYSTEM
    assert screen._active_phase == Phase.BASE_SYSTEM
    assert screen._bar.current == 30         # 3/10 → 30%


def test_emerge_marker_creeps_bar_within_a_step(screen):
    screen._on_step(4)                        # bar base = 40%
    screen._consume(">>> Emerging (5 of 10) dev-lang/python-3.12")
    # (4 + (5-1)/10) / 10 * 100 = 44
    assert screen._bar.current == 44
    assert "5 of 10" in screen._sub
    # Installing counts the package itself as done
    screen._consume(">>> Installing (6 of 10) dev-lang/python-3.12")
    assert screen._bar.current == 46


def test_non_progress_output_does_not_move_the_bar(screen):
    screen._on_step(4)
    screen._consume("Calculating dependencies ... done!")
    assert screen._bar.current == 40         # unchanged


def test_failure_marks_the_active_phase_failed(screen):
    screen._active_phase = Phase.KERNEL_BOOT
    screen._finish(False, "boom")
    assert screen._done is True
    assert screen._failed_phase == Phase.KERNEL_BOOT
    assert screen._phase_status(Phase.KERNEL_BOOT) == "failed"
    assert screen._phase_status(Phase.BASE_SYSTEM) == "done"
    assert screen._phase_status(Phase.FINISH) == "pending"


def test_branded_body_shows_logo_and_phases(screen):
    out = _render(screen)
    assert "Installing Gentoo" in out
    for ph in ("Prepare disk", "Base system", "Kernel & boot", "Finish"):
        assert ph in out


def test_tab_toggles_to_the_output_log(screen):
    assert screen._branded is True
    screen.handle_key("tab")
    assert screen._branded is False
    out = _render(screen)
    assert "Output" in out                   # the boxed log pane
    screen.handle_key("tab")
    assert screen._branded is True
