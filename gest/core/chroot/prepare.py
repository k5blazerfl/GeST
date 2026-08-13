"""The pseudo-filesystem mount/teardown sequence and the DNS copy, as pipelines.

Pure step builders (`pseudo_mount_steps`, `pseudo_unmount_steps`,
`resolv_copy_step`) plus two apply functions that run them through an `Executor`
on the direct/live-CD path. The mount order is the current Handbook sequence; the
teardown is its exact reverse (run, dev, sys, proc), lazily unmounted so it is
robust to partial state.

Teardown is **best-effort**: it is meant to run from a ``finally`` path after a
possibly-failed install, so it runs every unmount independently — a busy or
already-detached mount does not stop the others, and it never raises (it must not
mask the original failure). Preparation, by contrast, runs through ``run_steps``
and stops at the first error like every other apply pipeline.

Every entry point guards ``root`` with
:func:`gest.core.disk.mount.guard_target_root`, so it is confined to ``/mnt`` /
``/media`` / ``/run/media`` and can never target ``/``.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable

from gest.core.chroot import commands
from gest.core.disk import mount
from gest.core.exec.executor import Executor
from gest.core.exec.runner import OnProgress
from gest.core.exec.steps import Step, run_steps


def _under(root: str, sub: str) -> str:
    """The absolute path of ``sub`` inside target ``root`` (``/mnt/gentoo`` + ``proc``)."""
    return root.rstrip("/") + "/" + sub.lstrip("/")


def pseudo_mount_steps(root: str) -> list[Step]:
    """The ordered Handbook pseudo-fs mounts under ``root``.

    Per target: create the mountpoint, then mount. proc first; ``/sys`` and
    ``/dev`` are recursive binds made ``rslave`` (so ``/dev/pts`` and ``/dev/shm``
    come along and events don't leak into the host); ``/run`` is a plain bind made
    ``slave``.
    """
    proc = _under(root, "proc")
    sys_ = _under(root, "sys")
    dev = _under(root, "dev")
    run = _under(root, "run")
    return [
        Step(f"create {proc}", commands.mkdir_p_argv(proc)),
        Step(f"mount proc at {proc}", commands.mount_proc_argv(proc)),
        Step(f"create {sys_}", commands.mkdir_p_argv(sys_)),
        Step(f"rbind /sys → {sys_}", commands.mount_pseudo_argv("/sys", sys_, rbind=True)),
        Step(f"make {sys_} rslave", commands.make_propagation_argv(sys_, "rslave")),
        Step(f"create {dev}", commands.mkdir_p_argv(dev)),
        Step(f"rbind /dev → {dev}", commands.mount_pseudo_argv("/dev", dev, rbind=True)),
        Step(f"make {dev} rslave", commands.make_propagation_argv(dev, "rslave")),
        Step(f"create {run}", commands.mkdir_p_argv(run)),
        Step(f"bind /run → {run}", commands.mount_pseudo_argv("/run", run, rbind=False)),
        Step(f"make {run} slave", commands.make_propagation_argv(run, "slave")),
    ]


def pseudo_unmount_steps(root: str) -> list[Step]:
    """Lazily unmount the pseudo-filesystems in reverse order (run, dev, sys, proc).

    The recursive binds (``/dev``, ``/sys``) get a recursive lazy unmount so their
    submounts go too; ``/run`` and proc get a plain lazy unmount.
    """
    run = _under(root, "run")
    dev = _under(root, "dev")
    sys_ = _under(root, "sys")
    proc = _under(root, "proc")
    return [
        Step(f"unmount {run}", commands.umount_lazy_argv(run)),
        Step(f"unmount {dev}", commands.umount_lazy_argv(dev, recursive=True)),
        Step(f"unmount {sys_}", commands.umount_lazy_argv(sys_, recursive=True)),
        Step(f"unmount {proc}", commands.umount_lazy_argv(proc)),
    ]


def resolv_copy_step(root: str) -> Step:
    """Copy the live CD's ``/etc/resolv.conf`` into ``<root>/etc/resolv.conf``.

    So ``emerge`` resolves mirrors from inside the chroot. Distinct from the
    persistent ``core/network/resolv.py`` config the user chooses for the
    installed system — this is the transient live DNS, copied for the build.
    """
    dest = _under(root, "etc/resolv.conf")
    return Step(f"copy resolv.conf → {dest}", commands.cp_resolv_argv(root))


async def prepare_chroot(
    root: str,
    executor: Executor,
    *,
    on_progress: OnProgress | None = None,
    on_step: Callable[[int], None] | None = None,
) -> list[Step]:
    """Mount the pseudo-filesystems and copy DNS into ``root``, in Handbook order.

    Guards the root, then runs the mounts followed by the resolv.conf copy through
    ``executor``. Raises :class:`gest.core.exec.steps.StepError` at the first step
    that exits non-zero (so the caller can trigger teardown). Returns the steps run.
    """
    mount.guard_target_root(root)
    steps = [*pseudo_mount_steps(root), resolv_copy_step(root)]
    return await run_steps(steps, executor, on_progress=on_progress, on_step=on_step)


async def teardown_chroot(
    root: str,
    executor: Executor,
    *,
    on_progress: OnProgress | None = None,
    on_step: Callable[[int], None] | None = None,
) -> list[Step]:
    """Best-effort lazy-unmount of the pseudo-filesystems under ``root``.

    Built for a ``finally`` path: each unmount runs independently, a failure does
    not stop the rest, and the function never raises (a lazy unmount of an
    already-gone path is effectively a no-op). Returns the steps it attempted, in
    teardown order.
    """
    mount.guard_target_root(root)
    steps = pseudo_unmount_steps(root)
    for index, step in enumerate(steps):
        if on_step is not None:
            on_step(index)
        with contextlib.suppress(Exception):
            await executor.run(step.argv, on_progress=on_progress)
    return steps
