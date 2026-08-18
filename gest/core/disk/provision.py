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

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from gest.core.disk import commands
from gest.core.disk.model import BlockDevice, DiskPlan, Filesystem, Partition
from gest.core.exec.executor import Executor
from gest.core.exec.runner import OnProgress, RunResult


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


def root_source(proc_mounts_text: str) -> str | None:
    """The device mounted at ``/`` — the one we must never provision over."""
    for line in proc_mounts_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "/" and parts[0].startswith("/dev/"):
            return parts[0]
    return None


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


def guard_provision_target(
    device: str, proc_mounts_text: str, *, whole_disk: bool
) -> None:
    """Raise :class:`DiskSafetyError` if ``device`` is unsafe to provision.

    The authoritative, server-side re-check the backend runs before every
    destructive op — the untrusted frontend's own validation is only a
    convenience. ``whole_disk`` widens the check to any partition on the disk
    (for partitioning); otherwise it guards the single partition (for mkfs/swap).
    A mounted target, or the device backing ``/`` (the running/live system), is
    always refused.
    """
    problems: list[str] = []
    mounts = mounted_sources(proc_mounts_text)
    root = root_source(proc_mounts_text)
    if whole_disk:
        hit = next((src for src in mounts if _touches(src, device)), None)
        if hit is not None:
            problems.append(f"{device} has a mounted partition ({hit})")
        if root and _touches(root, device):
            problems.append(f"{device} backs the running system and cannot be repartitioned")
    else:
        if device in mounts:
            problems.append(f"{device} is mounted")
        if root and device == root:
            problems.append(f"{device} is the running root filesystem")
    if problems:
        raise DiskSafetyError(problems)


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
    """The ordered pipeline for ``plan``: wipe → partition → settle → mkfs/mkswap.

    Swap is **formatted** here (``mkswap``) but not activated — the mount step
    (:func:`mount.mount_steps`) ``swapon``s it. Doing both double-activates and the
    second ``swapon`` fails "Device or resource busy".
    """
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
        else:
            steps.append(Step(f"make {fs.kind} on {fs.device}",
                              commands.mkfs_argv(fs.device, fs.kind, fs.label)))
    return steps


def partition_device(disk_name: str, number: int) -> str:
    """The partition node for ``number`` on ``disk_name`` (sda2, nvme0n1p2)."""
    sep = "p" if disk_name[-1:].isdigit() else ""
    return f"/dev/{disk_name}{sep}{number}"


def uefi_plan(disk_name: str, esp_size: str, swap_size: str, root_fs: str) -> DiskPlan:
    """Build a GPT/UEFI ``DiskPlan``: ESP + optional swap + root (fills the rest).

    ``swap_size`` empty means no swap. Raises ``ValueError`` on an unsupported
    root filesystem or a size/label the argv builders reject (checked eagerly via
    :func:`plan_steps`).
    """
    if root_fs not in commands.FS_KINDS or root_fs == "swap":
        raise ValueError(f"unsupported root filesystem: {root_fs!r}")
    partitions: list[Partition] = []
    filesystems: list[Filesystem] = []
    number = 1
    partitions.append(Partition(number, esp_size, "EF00", "ESP"))
    filesystems.append(Filesystem(partition_device(disk_name, number), "vfat", "ESP"))
    number += 1
    if swap_size:
        partitions.append(Partition(number, swap_size, "8200", "swap"))
        filesystems.append(Filesystem(partition_device(disk_name, number), "swap", "swap"))
        number += 1
    partitions.append(Partition(number, "rest", "8300", "root"))
    filesystems.append(Filesystem(partition_device(disk_name, number), root_fs, "root"))
    plan = DiskPlan(disk=f"/dev/{disk_name}", wipe=True,
                    partitions=partitions, filesystems=filesystems)
    plan_steps(plan)          # validate sizes/labels eagerly; raises ValueError
    return plan


def plan_phase_labels(plan: DiskPlan) -> list[str]:
    """Coarse, one-per-phase labels for the backend path (and the apply UI).

    Matches the phases :func:`apply_via_backend` walks: one partition phase, then
    one per filesystem (a swap phase covers both mkswap and swapon).
    """
    labels = [f"Partition {plan.disk}"]
    for fs in plan.filesystems:
        if fs.kind == "swap":
            labels.append(f"Enable swap on {fs.device}")
        else:
            labels.append(f"Make {fs.kind} on {fs.device}")
    return labels


async def apply_plan(
    plan: DiskPlan,
    executor: Executor,
    devices: list[BlockDevice],
    proc_mounts_text: str,
    *,
    boot_source: str | None = None,
    on_progress: OnProgress | None = None,
    on_step: Callable[[int], None] | None = None,
) -> list[Step]:
    """Validate ``plan`` and run its pipeline through ``executor``.

    Raises :class:`DiskSafetyError` before running anything if validation fails,
    or :class:`DiskApplyError` at the first step that exits non-zero. ``on_step``
    is called with each step's index as it starts (for progress UI). Returns the
    steps that ran on success.
    """
    problems = validate_plan(plan, devices, proc_mounts_text, boot_source=boot_source)
    if problems:
        raise DiskSafetyError(problems)
    steps = plan_steps(plan)
    for index, step in enumerate(steps):
        if on_step is not None:
            on_step(index)
        result = await executor.run(step.argv, on_progress=on_progress)
        if result.code != 0:
            raise DiskApplyError(step, result)
    return steps


class DiskProvisioner(Protocol):
    """The backend calls the frontend makes on the installed-system (D-Bus) path.

    Each method mirrors a root ``org.gentoo.gest.Disk`` provisioning method and
    returns ``(ok, output)``. Implemented by ``core/disk/backend_client``; a fake
    stands in for tests.
    """

    async def partition_disk(
        self, disk: str, wipe: bool, partitions: list[tuple[int, str, str, str]]
    ) -> tuple[bool, str]: ...

    async def make_filesystem(self, device: str, kind: str, label: str) -> tuple[bool, str]: ...

    async def make_swap(self, device: str, label: str) -> tuple[bool, str]: ...

    async def swapon(self, device: str) -> tuple[bool, str]: ...


async def apply_via_backend(
    plan: DiskPlan,
    backend: DiskProvisioner,
    *,
    on_progress: OnProgress | None = None,
    on_step: Callable[[int], None] | None = None,
) -> None:
    """Apply ``plan`` through the root backend (installed-system path).

    The same plan, same order (partition → filesystems/swap) as the direct path,
    but each phase is a polkit-gated backend call that re-validates server-side.
    ``on_step`` is called with each phase index as it starts (see
    :func:`plan_phase_labels`). Raises :class:`DiskApplyError` at the first phase
    the backend refuses or that fails. (Callers should still pre-validate with
    :func:`validate_plan` for a friendly message; the backend guard is the
    authoritative one.)
    """

    def _fail(label: str, output: str) -> DiskApplyError:
        return DiskApplyError(Step(label, []), RunResult(1, output))

    def _emit(output: str) -> None:
        if on_progress and output:
            on_progress(output.splitlines())

    def _step(index: int) -> None:
        if on_step is not None:
            on_step(index)

    _step(0)
    partitions = [(p.number, p.size, p.type_guid, p.label or "") for p in plan.partitions]
    ok, out = await backend.partition_disk(plan.disk, plan.wipe, partitions)
    _emit(out)
    if not ok:
        raise _fail(f"partition {plan.disk}", out)

    for phase, fs in enumerate(plan.filesystems, start=1):
        _step(phase)
        if fs.kind == "swap":
            # Format only — the mount step swapons it; doing both fails "busy".
            ok, out = await backend.make_swap(fs.device, fs.label or "")
            _emit(out)
            if not ok:
                raise _fail(f"make swap on {fs.device}", out)
        else:
            ok, out = await backend.make_filesystem(fs.device, fs.kind, fs.label or "")
            _emit(out)
            if not ok:
                raise _fail(f"make {fs.kind} on {fs.device}", out)
