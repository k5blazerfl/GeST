"""Apply a `DiskPlan` safely: validate targets, then run an ordered pipeline.

This is the dangerous heart of the partitioner, so it is built to be inspected
without touching a disk:

* `validate_plan` re-checks every device target against the real block-device
  tree and `/proc/mounts` — it refuses a device that is mounted, that backs the
  running root, or that is the live medium GeST booted from. The UI validates too
  for a friendly message, but *this* check is the contract (same discipline as
  the fstab/backend guards).
* `plan_steps` turns a plan into a fixed, ordered list of `Step`s
  (wipe → partition → settle → mkfs/swap). The ordering — and the settle step,
  the usual source of "device busy" flakiness — lives here, in one pure function
  a test can assert on.
* `apply_plan` runs those steps through an `Executor` (D-Bus on an installed
  system, direct/in-process on a live CD — see `gest.core.exec`).
"""

from __future__ import annotations

from dataclasses import dataclass

from gest.core.disk import commands
from gest.core.disk.model import BlockDevice, DiskPlan
from gest.core.exec.executor import Executor
from gest.core.exec.runner import RunResult


@dataclass(slots=True, frozen=True)
class Step:
    """One command in the apply pipeline: a human label and the argv to run."""

    label: str
    argv: list[str]


class DiskSafetyError(Exception):
    """A plan failed validation; ``problems`` lists every reason (never runs)."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


class DiskApplyError(Exception):
    """A step exited non-zero; the pipeline stops at the first failure."""

    def __init__(self, step: Step, result: RunResult) -> None:
        self.step = step
        self.result = result
        super().__init__(f"{step.label} failed (exit {result.code})")


def mounted_sources(proc_mounts_text: str) -> set[str]:
    """The source device of every current mount (field 1 of /proc/mounts)."""
    sources: set[str] = set()
    for line in proc_mounts_text.splitlines():
        parts = line.split()
        if parts and parts[0].startswith("/dev/"):
            sources.add(parts[0])
    return sources


def _device_names(devices: list[BlockDevice], prefix: str = "/dev/") -> set[str]:
    """Every device path in an lsblk tree, walked recursively."""
    names: set[str] = set()
    for dev in devices:
        names.add(prefix + dev.name)
        names |= _device_names(dev.children, prefix)
    return names


def _touches(source: str, disk: str) -> bool:
    """True if ``source`` is the disk itself or a partition on it."""
    return source == disk or source.startswith(disk)


def validate_plan(
    plan: DiskPlan,
    devices: list[BlockDevice],
    proc_mounts_text: str,
    *,
    boot_source: str | None = None,
) -> list[str]:
    """Return a list of safety problems with ``plan`` — empty means safe to run.

    ``devices`` is the live `lsblk` tree, ``proc_mounts_text`` the contents of
    /proc/mounts, and ``boot_source`` the device the live medium booted from (if
    known) so we never repartition the disk we're running off.
    """
    problems: list[str] = []
    known = _device_names(devices)

    if plan.disk not in known:
        problems.append(f"{plan.disk} is not a present block device")

    for source in mounted_sources(proc_mounts_text):
        if _touches(source, plan.disk):
            problems.append(f"{plan.disk} has a mounted partition ({source})")
            break

    if boot_source and _touches(boot_source, plan.disk):
        problems.append(f"{plan.disk} is the live/boot medium and cannot be repartitioned")

    # Surface any builder-level rejection (bad size/GUID/label/device) as a
    # safety problem rather than letting it raise mid-apply.
    try:
        plan_steps(plan)
    except ValueError as exc:
        problems.append(str(exc))

    return problems


def plan_steps(plan: DiskPlan) -> list[Step]:
    """The ordered pipeline for ``plan``: wipe → partition → settle → mkfs/swap."""
    steps: list[Step] = []
    if plan.wipe:
        steps.append(Step(f"wipe signatures on {plan.disk}", commands.wipefs_argv(plan.disk)))
        steps.append(Step(f"zap partition table on {plan.disk}",
                          commands.sgdisk_zap_argv(plan.disk)))
    steps.append(Step(f"create partitions on {plan.disk}",
                      commands.sgdisk_partition_argv(plan.disk, plan.partitions)))
    steps.append(Step("re-read partition table", commands.partprobe_argv(plan.disk)))
    steps.append(Step("settle udev", commands.udevadm_settle_argv()))
    for fs in plan.filesystems:
        if fs.kind == "swap":
            steps.append(Step(f"make swap on {fs.device}",
                              commands.mkswap_argv(fs.device, fs.label)))
            steps.append(Step(f"enable swap on {fs.device}", commands.swapon_argv(fs.device)))
        else:
            steps.append(Step(f"make {fs.kind} on {fs.device}",
                              commands.mkfs_argv(fs.device, fs.kind, fs.label)))
    return steps


async def apply_plan(
    plan: DiskPlan,
    executor: Executor,
    devices: list[BlockDevice],
    proc_mounts_text: str,
    *,
    boot_source: str | None = None,
    on_progress=None,
) -> list[Step]:
    """Validate ``plan`` and run its pipeline through ``executor``.

    Raises :class:`DiskSafetyError` before running anything if validation fails,
    or :class:`DiskApplyError` at the first step that exits non-zero. Returns the
    steps that ran on success.
    """
    problems = validate_plan(plan, devices, proc_mounts_text, boot_source=boot_source)
    if problems:
        raise DiskSafetyError(problems)
    steps = plan_steps(plan)
    for step in steps:
        result = await executor.run(step.argv, on_progress=on_progress)
        if result.code != 0:
            raise DiskApplyError(step, result)
    return steps
