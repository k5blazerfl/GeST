"""Assemble an install target from freshly-made filesystems, and generate its
fstab — the bridge from "partitioned disk" to "installable system".

After the partitioner has created partitions and filesystems on a disk, this
module mounts them under a *target root* (``/mnt/gentoo`` by convention), enables
swap, and writes that system's own ``/etc/fstab`` keyed by UUID. Like the rest of
the disk module it is split so the dangerous parts are inspectable:

* everything about *which* device mounts *where* (`derive_mount_plan`), the
  ordered mkdir→mount→swapon pipeline (`mount_steps`), and what a safe target
  root is (`valid_target_root`) lives here as pure, CI-testable functions;
* applying runs through an `Executor` (direct/in-process as root on a live CD,
  or the polkit-gated backend on an installed system) — the same dual path as
  the partitioner;
* the generated fstab is built from the plan plus a device→UUID map
  (`generate_target_fstab`) and re-validated before any privileged write.

Safety: a target root is confined to the ``/mnt`` / ``/media`` / ``/run/media``
prefixes so a mount or an fstab write can never land on the running system.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from gest.core.disk import commands, fstab
from gest.core.disk.model import DiskPlan
from gest.core.exec.executor import Executor
from gest.core.exec.runner import OnProgress
from gest.core.exec.steps import Step, fail, run_steps

# Where an install target may be assembled. Never the running system's own tree.
ALLOWED_TARGET_ROOTS = ("/mnt", "/media", "/run/media")

# Filesystem label (role) -> the mount path it takes on the installed system.
# The canned UEFI plan labels its filesystems "ESP"/"root"; a custom layout can
# use any of these roles, and an unknown label falls back to "/<label>".
ROLE_TO_PATH: dict[str, str] = {
    "root": "/",
    "esp": "/efi",
    "boot": "/boot",
    "home": "/home",
    "var": "/var",
}


@dataclass(slots=True, frozen=True)
class TargetMount:
    """One filesystem to mount while building the install target.

    ``path`` is the mount point *on the installed system* (``/``, ``/efi``, …);
    the actual mount happens at ``target_abs(root, path)``.
    """

    device: str
    path: str
    fstype: str


@dataclass(slots=True, frozen=True)
class MountPlan:
    """A whole install-target mount: filesystems (root-first) + swap devices."""

    root: str
    mounts: list[TargetMount] = field(default_factory=list)
    swap: list[str] = field(default_factory=list)


# --- target-root safety -----------------------------------------------------

def valid_target_root(root: str) -> bool:
    """True if ``root`` is a safe place to assemble an install target.

    Must be a syntactically valid absolute path strictly under one of
    :data:`ALLOWED_TARGET_ROOTS` — so ``/mnt/gentoo`` is fine but ``/``,
    ``/home`` or ``/mnt`` itself are refused.
    """
    if not commands.valid_target_path(root):
        return False
    return any(root.startswith(prefix + "/") for prefix in ALLOWED_TARGET_ROOTS)


def guard_target_root(root: str) -> None:
    """Raise ``ValueError`` unless ``root`` is a valid target root."""
    if not valid_target_root(root):
        raise ValueError(f"unsafe target root: {root!r}")


def target_abs(root: str, path: str) -> str:
    """The absolute mount path for ``path`` under target ``root``.

    ``path == "/"`` is the target root itself; otherwise it is appended
    (``/mnt/gentoo`` + ``/efi`` -> ``/mnt/gentoo/efi``).
    """
    if path == "/":
        return root
    return root.rstrip("/") + path


# --- deriving a plan from a DiskPlan ----------------------------------------

def _role_path(label: str | None) -> str:
    key = (label or "").lower()
    if key in ROLE_TO_PATH:
        return ROLE_TO_PATH[key]
    if not label:
        raise ValueError("filesystem has no label/role; cannot derive a mount point")
    return "/" + key


def _mount_order(mount: TargetMount) -> tuple[int, str]:
    # Root first, then shallower paths before deeper ones (so a parent is always
    # mounted before anything nested inside it).
    return (0 if mount.path == "/" else mount.path.count("/"), mount.path)


def derive_mount_plan(disk_plan: DiskPlan, target_root: str) -> MountPlan:
    """Turn a just-applied :class:`DiskPlan` into a :class:`MountPlan`.

    Non-swap filesystems become ordered mounts (by role -> path); swap
    filesystems become ``swapon`` targets. Raises ``ValueError`` on an unsafe
    target root or a filesystem whose role can't be mapped to a mount point.
    """
    guard_target_root(target_root)
    mounts: list[TargetMount] = []
    swap: list[str] = []
    for fs in disk_plan.filesystems:
        if fs.kind == "swap":
            swap.append(fs.device)
        else:
            mounts.append(TargetMount(fs.device, _role_path(fs.label), fs.kind))
    mounts.sort(key=_mount_order)
    return MountPlan(root=target_root, mounts=mounts, swap=swap)


# --- the mkdir -> mount -> swapon pipeline ----------------------------------

def mount_steps(plan: MountPlan) -> list[Step]:
    """The ordered pipeline for ``plan``: per mount, mkdir then mount; swap last."""
    steps: list[Step] = []
    for mount in plan.mounts:
        dest = target_abs(plan.root, mount.path)
        steps.append(Step(f"create {dest}", commands.mkdir_p_argv(dest)))
        steps.append(Step(f"mount {mount.device} → {dest}",
                          commands.mount_device_argv(mount.device, dest)))
    for device in plan.swap:
        steps.append(Step(f"enable swap on {device}", commands.swapon_argv(device)))
    return steps


def mount_plan_labels(plan: MountPlan) -> list[str]:
    """One coarse label per phase for the backend path (and the apply UI).

    Matches the phases :func:`apply_mount_plan_via_backend` walks: one per mount,
    then one per swap device.
    """
    labels = [f"Mount {m.device} → {target_abs(plan.root, m.path)}" for m in plan.mounts]
    labels += [f"Enable swap on {d}" for d in plan.swap]
    return labels


async def apply_mount_plan(
    plan: MountPlan,
    executor: Executor,
    *,
    on_progress: OnProgress | None = None,
    on_step: Callable[[int], None] | None = None,
) -> list[Step]:
    """Run ``plan``'s mount pipeline through ``executor`` (direct/live-CD path).

    Raises :class:`gest.core.exec.steps.StepError` at the first step that exits
    non-zero. ``on_step`` is called with each step index as it starts.
    """
    guard_target_root(plan.root)
    return await run_steps(mount_steps(plan), executor,
                           on_progress=on_progress, on_step=on_step)


class TargetMounter(Protocol):
    """The backend calls the frontend makes on the installed-system (D-Bus) path.

    Implemented by ``core/disk/backend_client``; a fake stands in for tests. Each
    returns ``(ok, output)``.
    """

    async def mount_at(self, device: str, path: str) -> tuple[bool, str]: ...

    async def swapon(self, device: str) -> tuple[bool, str]: ...

    async def write_target_fstab(self, target: str, text: str) -> tuple[bool, str]: ...


async def apply_mount_plan_via_backend(
    plan: MountPlan,
    backend: TargetMounter,
    *,
    on_progress: OnProgress | None = None,
    on_step: Callable[[int], None] | None = None,
) -> None:
    """Apply ``plan`` through the root backend (installed-system path).

    Same order as the direct path (mounts, root-first, then swap); each phase is
    a polkit-gated backend call that re-validates server-side. Raises
    :class:`gest.core.exec.steps.StepError` at the first phase that fails.
    """
    guard_target_root(plan.root)

    def _emit(output: str) -> None:
        if on_progress and output:
            on_progress(output.splitlines())

    def _step(index: int) -> None:
        if on_step is not None:
            on_step(index)

    index = 0
    for mount in plan.mounts:
        _step(index)
        index += 1
        dest = target_abs(plan.root, mount.path)
        ok, out = await backend.mount_at(mount.device, dest)
        _emit(out)
        if not ok:
            raise fail(f"mount {mount.device} → {dest}", out)
    for device in plan.swap:
        _step(index)
        index += 1
        ok, out = await backend.swapon(device)
        _emit(out)
        if not ok:
            raise fail(f"enable swap on {device}", out)


# --- generating the target's fstab ------------------------------------------

def fstab_devices(plan: MountPlan) -> list[str]:
    """Every device in ``plan`` whose UUID a generated fstab needs (mounts + swap)."""
    return [m.device for m in plan.mounts] + list(plan.swap)


def generate_target_fstab(plan: MountPlan, uuids: dict[str, str]) -> str:
    """Render the install target's ``/etc/fstab`` from ``plan`` and device UUIDs.

    ``uuids`` maps each device (see :func:`fstab_devices`) to its filesystem UUID.
    Raises ``ValueError`` if any device is missing a UUID (we never fall back to a
    volatile ``/dev/…`` name in a generated fstab).
    """
    def uuid_for(device: str) -> str:
        uuid = uuids.get(device)
        if not uuid:
            raise ValueError(f"no UUID for {device}")
        return uuid

    entries = [fstab.gen_fstab_entry(uuid_for(m.device), m.path, m.fstype)
               for m in plan.mounts]
    entries += [fstab.gen_fstab_entry(uuid_for(d), "none", "swap") for d in plan.swap]
    return fstab.render_fstab(entries)


def write_target_fstab_file(target_root: str, text: str) -> str:
    """Write ``text`` to ``<target_root>/etc/fstab`` atomically (direct/root path).

    The in-process counterpart to the backend's ``WriteTargetFstab`` for when GeST
    is already root (live CD). Re-checks the target root and that ``text`` is a
    well-formed fstab before touching disk. Returns the path written.
    """
    guard_target_root(target_root)
    if not fstab.valid_generated_fstab(text):
        raise ValueError("refusing to write a malformed fstab")
    etc = os.path.join(target_root, "etc")
    os.makedirs(etc, exist_ok=True)
    path = os.path.join(etc, "fstab")
    fd, tmp = tempfile.mkstemp(dir=etc, prefix=".gest.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return path
