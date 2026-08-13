"""CI-safe tests for the chroot primitives: the `ChrootExecutor` argv wrap, the
pseudo-filesystem mount/teardown step builders, the DNS copy, and the
prepare/teardown apply paths. No real mounts — everything runs through a
FakeExecutor, and the target-root guard (reject ``/``) is asserted at every
entry point."""

import asyncio

import pytest

from gest.core.chroot import commands, prepare
from gest.core.exec.chroot import ChrootExecutor
from gest.core.exec.executor import FakeExecutor
from gest.core.exec.runner import RunResult

ROOT = "/mnt/gentoo"


# --- ChrootExecutor ---------------------------------------------------------

def test_chroot_executor_wraps_argv():
    fake = FakeExecutor()
    ex = ChrootExecutor(fake, ROOT)
    result = asyncio.run(ex.run(["emerge", "--sync"]))
    assert fake.calls == [["chroot", ROOT, "emerge", "--sync"]]
    assert isinstance(result, RunResult) and result.code == 0


def test_chroot_executor_forwards_progress_and_returns_inner_result():
    fake = FakeExecutor(code_for=lambda argv: 42)
    ex = ChrootExecutor(fake, ROOT)
    seen: list[str] = []
    result = asyncio.run(ex.run(["eselect", "profile", "list"], on_progress=seen.extend))
    # FakeExecutor echoes the *wrapped* argv into on_progress, and its code flows back.
    assert seen == ["$ chroot /mnt/gentoo eselect profile list"]
    assert result.code == 42


def test_chroot_executor_rejects_running_system():
    for bad in ("/", "/home", "/mnt", "relative/path", "/mnt/../etc"):
        with pytest.raises(ValueError):
            ChrootExecutor(FakeExecutor(), bad)


# --- pseudo-fs mount ordering + argv ----------------------------------------

def test_pseudo_mount_steps_order_and_argv():
    argvs = [s.argv for s in prepare.pseudo_mount_steps(ROOT)]
    assert argvs == [
        ["mkdir", "-p", "/mnt/gentoo/proc"],
        ["mount", "-t", "proc", "proc", "/mnt/gentoo/proc"],
        ["mkdir", "-p", "/mnt/gentoo/sys"],
        ["mount", "--rbind", "/sys", "/mnt/gentoo/sys"],
        ["mount", "--make-rslave", "/mnt/gentoo/sys"],
        ["mkdir", "-p", "/mnt/gentoo/dev"],
        ["mount", "--rbind", "/dev", "/mnt/gentoo/dev"],
        ["mount", "--make-rslave", "/mnt/gentoo/dev"],
        ["mkdir", "-p", "/mnt/gentoo/run"],
        ["mount", "--bind", "/run", "/mnt/gentoo/run"],
        ["mount", "--make-slave", "/mnt/gentoo/run"],
    ]


def test_pseudo_mount_creates_mountpoint_before_mounting_and_targets_under_root():
    steps = prepare.pseudo_mount_steps(ROOT)
    for name in ("proc", "sys", "dev", "run"):
        target = f"{ROOT}/{name}"
        mkdir_at = next(i for i, s in enumerate(steps)
                        if s.argv == ["mkdir", "-p", target])
        mount_at = next(i for i, s in enumerate(steps)
                        if s.argv[0] == "mount" and s.argv[-1] == target)
        assert mkdir_at < mount_at
    # Every path the pipeline touches is strictly under the target root.
    for step in steps:
        assert step.argv[-1].startswith(ROOT + "/")


def test_pseudo_unmount_steps_reverse_order_and_lazy():
    argvs = [s.argv for s in prepare.pseudo_unmount_steps(ROOT)]
    assert argvs == [
        ["umount", "-l", "/mnt/gentoo/run"],
        ["umount", "-R", "-l", "/mnt/gentoo/dev"],
        ["umount", "-R", "-l", "/mnt/gentoo/sys"],
        ["umount", "-l", "/mnt/gentoo/proc"],
    ]


def test_resolv_copy_step_argv():
    step = prepare.resolv_copy_step(ROOT)
    assert step.argv == [
        "cp", "--dereference", "/etc/resolv.conf", "/mnt/gentoo/etc/resolv.conf",
    ]


# --- command builder validation ---------------------------------------------

def test_command_builders_reject_unsafe_paths():
    with pytest.raises(ValueError):
        commands.mkdir_p_argv("relative")
    with pytest.raises(ValueError):
        commands.mount_proc_argv("/mnt/../etc")
    with pytest.raises(ValueError):
        commands.umount_lazy_argv("../up")
    with pytest.raises(ValueError):
        commands.make_propagation_argv(ROOT, "private")  # only rslave/slave allowed


# --- prepare / teardown apply paths -----------------------------------------

def test_prepare_chroot_runs_mounts_then_resolv_in_order():
    fake = FakeExecutor()
    steps = asyncio.run(prepare.prepare_chroot(ROOT, fake))
    expected = [s.argv for s in prepare.pseudo_mount_steps(ROOT)]
    expected.append(prepare.resolv_copy_step(ROOT).argv)
    assert fake.calls == expected
    assert [s.argv for s in steps] == expected


def test_teardown_chroot_runs_unmounts_in_order():
    fake = FakeExecutor()
    asyncio.run(prepare.teardown_chroot(ROOT, fake))
    assert fake.calls == [s.argv for s in prepare.pseudo_unmount_steps(ROOT)]


def test_teardown_is_best_effort_and_never_raises():
    # Every unmount "fails" (non-zero) and one call raises — teardown must still
    # attempt all four and not propagate.
    def code_for(argv):
        if argv[-1].endswith("/dev"):
            raise OSError("umount binary missing")
        return 32  # umount's "not mounted" style failure

    fake = FakeExecutor(code_for=code_for)
    steps = asyncio.run(prepare.teardown_chroot(ROOT, fake))
    assert len(fake.calls) == 4              # all attempted despite failures
    assert len(steps) == 4


def test_prepare_and_teardown_reject_running_system():
    for bad in ("/", "/home", "/mnt"):
        with pytest.raises(ValueError):
            asyncio.run(prepare.prepare_chroot(bad, FakeExecutor()))
        with pytest.raises(ValueError):
            asyncio.run(prepare.teardown_chroot(bad, FakeExecutor()))
