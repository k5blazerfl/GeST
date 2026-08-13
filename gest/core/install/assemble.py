"""Turn the installer's editable selections into a reviewed ``InstallPlan``.

The installer UI holds a mutable :class:`InstallSelections`; pressing *Install*
resolves the stage3 variant to a concrete download (`resolve_stage3`, the one bit
of I/O) and then assembles the frozen :class:`InstallPlan` (`assemble_plan`,
pure). Keeping assembly pure means the whole "selections → plan" mapping is
unit-testable without a TUI or a network — the plan is a value, like ``DiskPlan``.

The root password is deliberately NOT a plan field: it lives on the selections as
an in-memory secret and is handed to ``build_registry(plan, root_secret=…)`` at
run time, so a plan is safe to log, diff and snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass

from gest.core.bootloader.install import InstallConfig
from gest.core.disk import mount as disk_mount
from gest.core.disk import provision
from gest.core.install.plan import InstallPlan
from gest.core.kernel.build import BuildConfig
from gest.core.stage3 import index
from gest.core.stage3.model import DEFAULT_VARIANT, Stage3Selection, Stage3Variant

DEFAULT_TARGET_ROOT = "/mnt/gentoo"


@dataclass(slots=True)
class InstallSelections:
    """The installer overview's editable state (mutable; the UI edits it in place).

    5a wires the boot-critical rows (disk, stage3, kernel, bootloader, root
    password); the system fields carry sane defaults that later steps make
    editable. ``root_password`` is the actual secret, kept only in memory.
    """

    # disk (a GPT/UEFI layout: ESP + optional swap + root fills the rest)
    disk: str = ""                    # device name, e.g. "sda"
    esp_size: str = "512M"
    swap_size: str = "8G"             # "" = no swap
    root_fs: str = "ext4"
    target_root: str = DEFAULT_TARGET_ROOT
    # stage3
    variant: Stage3Variant = DEFAULT_VARIANT
    # system (defaults for 5a; editable rows land in 5b)
    hostname: str = "gentoo"
    timezone: str = "UTC"
    locale: str = "C.UTF-8"
    keymap: str = "us"
    # kernel
    kernel_method: str = "make"       # "make" | "genkernel"
    kernel_jobs: int = 0              # 0 → the module resolves to CPU count
    kernel_initramfs: bool = True
    # bootloader
    firmware: str = "uefi"            # "uefi" | "bios"
    efi_directory: str = "/efi"
    boot_disk: str = ""               # BIOS target disk (firmware == "bios")
    # secret + toggles
    root_password: str = ""           # in-memory only; never in the plan
    binary_pref: bool = True          # --getbinpkg for @world


def resolve_stage3(variant: Stage3Variant, *, mirror: str = index.MIRROR) -> Stage3Selection:
    """Resolve a variant to a concrete download via the mirror's latest index (I/O).

    Fetches ``latest-stage3-<flavor>.txt``, parses the current tarball path + size,
    and derives the tarball / ``.DIGESTS`` / ``.asc`` URLs. Raises on a network or
    parse failure (the caller surfaces it).
    """
    latest = index.fetch_text(index.latest_url(mirror, variant.arch, variant.flavor))
    relpath, size = index.parse_latest(latest)
    tarball = index.tarball_url(mirror, variant.arch, relpath)
    return Stage3Selection(
        url=tarball,
        filename=relpath.rsplit("/", 1)[-1],
        size=size,
        digests_url=index.digests_url(tarball),
        signature_url=index.signature_url(tarball),
    )


def assemble_plan(sel: InstallSelections, stage3: Stage3Selection) -> InstallPlan:
    """Build the frozen :class:`InstallPlan` from ``sel`` and a resolved ``stage3``.

    Pure: no I/O. Raises ``ValueError`` on a selection the module validators reject
    (empty disk, bad filesystem/size, empty root password, bad firmware).
    """
    if not sel.disk:
        raise ValueError("no target disk selected")
    if not sel.root_password:
        raise ValueError("a root password is required")
    if sel.firmware not in ("uefi", "bios"):
        raise ValueError(f"invalid firmware: {sel.firmware!r}")
    disk = provision.uefi_plan(sel.disk, sel.esp_size, sel.swap_size, sel.root_fs)
    mount = disk_mount.derive_mount_plan(disk, sel.target_root)
    return InstallPlan(
        disk=disk,
        mount=mount,
        stage3=stage3,
        kernel=BuildConfig(
            method=sel.kernel_method, jobs=sel.kernel_jobs, initramfs=sel.kernel_initramfs),
        bootloader=InstallConfig(
            firmware=sel.firmware, efi_directory=sel.efi_directory, disk=sel.boot_disk),
        hostname=sel.hostname,
        timezone=sel.timezone,
        locale=sel.locale,
        keymap=sel.keymap,
        binary_pref=sel.binary_pref,
    )
