"""CI-safe tests for the install flow engine mechanics (step 4a): run_install
runs steps in order, picks host-vs-chroot correctly, skips satisfied steps, and
always tears the pseudo-filesystems down — driven by a FakeExecutor, no real
mounts, no module calls."""

import asyncio

import pytest

from gest.core.chroot import prepare
from gest.core.exec.chroot import ChrootExecutor
from gest.core.exec.executor import FakeExecutor
from gest.core.exec.steps import Step, StepError
from gest.core.install.context import InstallContext, StateStore
from gest.core.install.engine import run_install
from gest.core.install.plan import Phase
from gest.core.install.step import ArgvStep, FuncStep

_ROOT = "/mnt/gentoo"


class _HostStep(ArgvStep):
    label = "host op"
    phase = Phase.PREPARE_DISK
    target_aware = True

    def build(self, ctx):
        return [Step("mount root", ["mount", "/dev/sda3", _ROOT])]


class _PrepareStep(FuncStep):
    label = "prepare chroot"
    phase = Phase.BASE_SYSTEM
    opens_chroot = True

    async def run(self, ctx, on_progress=None):
        await prepare.prepare_chroot(ctx.root, ctx.host, on_progress=on_progress)


class _ChrootStep(ArgvStep):
    label = "emerge @world"
    phase = Phase.BASE_SYSTEM
    chroot = True

    def build(self, ctx):
        return [Step("emerge", ["emerge", "-uDN", "@world"])]


class _SatisfiedStep(ArgvStep):
    label = "already done"
    phase = Phase.CONFIGURE

    def build(self, ctx):
        return [Step("nope", ["should-not-run"])]

    async def is_satisfied(self, ctx):
        return True


def _ctx(executor):
    return InstallContext(root=_ROOT, host=executor,
                          target=ChrootExecutor(executor, _ROOT), state=StateStore())


def _run(executor, steps, **kw):
    asyncio.run(run_install(_ctx(executor), steps, **kw))


def test_runs_in_order_host_then_chroot_then_teardown():
    fx = FakeExecutor()
    started: list[int] = []
    _run(fx, [_HostStep(), _PrepareStep(), _ChrootStep()], on_step=started.append)

    calls = fx.calls
    # host step ran first, un-prefixed
    assert calls[0] == ["mount", "/dev/sda3", _ROOT]
    # the chroot step is wrapped by ChrootExecutor
    chroot_call = next(c for c in calls if c[:1] == ["chroot"])
    assert chroot_call == ["chroot", _ROOT, "emerge", "-uDN", "@world"]
    ci = calls.index(chroot_call)
    # prepare_chroot's mounts ran (on the host) before the chroot step
    assert ["mount", "-t", "proc", "proc", f"{_ROOT}/proc"] in calls[:ci]
    # teardown ran in the finally, after the chroot step
    umounts = [i for i, c in enumerate(calls) if c[:1] == ["umount"]]
    assert umounts and min(umounts) > ci
    assert [f"{_ROOT}/run" in c for c in calls if c[:1] == ["umount"]]  # run unmounted
    # every step was reported started, in order
    assert started == [0, 1, 2]


def test_host_steps_are_not_chroot_prefixed():
    fx = FakeExecutor()
    _run(fx, [_HostStep()])
    assert fx.calls == [["mount", "/dev/sda3", _ROOT]]
    assert all(c[:1] != ["chroot"] for c in fx.calls)


def test_satisfied_step_is_skipped():
    fx = FakeExecutor()
    started: list[int] = []
    progress: list[str] = []
    _run(fx, [_SatisfiedStep(), _HostStep()],
         on_step=started.append, on_progress=progress.extend)
    # the satisfied step's argv never ran; only the host step did
    assert fx.calls == [["mount", "/dev/sda3", _ROOT]]
    assert started == [1]                               # index 0 skipped, index 1 started
    assert any("already done" in line for line in progress)


def test_failure_stops_pipeline_but_teardown_still_runs():
    # fail the emerge (its wrapped argv contains "emerge")
    fx = FakeExecutor(code_for=lambda argv: 1 if "emerge" in argv else 0)
    # a trailing host step that must NOT run once the emerge fails
    with pytest.raises(StepError):
        _run(fx, [_HostStep(), _PrepareStep(), _ChrootStep(), _HostStep()])
    calls = fx.calls
    # the failing chroot emerge was attempted
    assert any(c[:1] == ["chroot"] and "emerge" in c for c in calls)
    # teardown still ran (finally), despite the failure
    assert any(c[:1] == ["umount"] for c in calls)
    # nothing after the failing step ran: only the first host step's "mount /dev/sda3"
    assert sum(1 for c in calls if c == ["mount", "/dev/sda3", _ROOT]) == 1


def test_state_marks_completed_steps():
    fx = FakeExecutor()
    ctx = _ctx(fx)
    asyncio.run(run_install(ctx, [_HostStep()]))
    assert ctx.state.done("host op")
    assert not ctx.state.done("emerge @world")
