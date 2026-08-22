"""The ``InstallPlan`` value type — the reviewed, approved plan for one install.

A plain frozen value (like ``DiskPlan``/``MountPlan``), so the whole run is
inspectable, diffable and testable before a single step executes. The engine
builds its ordered step registry from an ``InstallPlan`` and runs only an approved
one. Secrets are deliberately not in it: ``root_password`` is a boolean; the actual
password is supplied to the step at run time (never stored, so a plan is safe to
log and snapshot).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from gest.core.bootloader.install import InstallConfig
from gest.core.disk.model import DiskPlan
from gest.core.disk.mount import MountPlan
from gest.core.kernel.build import BuildConfig
from gest.core.stage3.model import Stage3Selection


class Phase(Enum):
    """The six Handbook-ordered phases a step belongs to (drives the UI headers)."""

    PREPARE_DISK = "Prepare disk"
    BASE_SYSTEM = "Base system"
    CONFIGURE = "Configure"
    KERNEL_BOOT = "Kernel & boot"
    USERS_NETWORK = "Users & network"
    FINISH = "Finish"


# ACCEPT_LICENSE policy: the wizard's 3-rung license choice → the make.conf value.
# @BINARY-REDISTRIBUTABLE is a superset of @FREE (it literally starts with @FREE)
# and already covers firmware + the proprietary NVIDIA driver (NVIDIA-r2) with no
# click-throughs; @EULA is the disjoint click-through pile (chrome/cuda/…). See
# docs — the Desktop default is Full so the review gate has nothing to reconcile.
LICENSE_POLICIES: dict[str, str] = {
    "libre": "@FREE",
    "redistributable": "@BINARY-REDISTRIBUTABLE",
    "full": "@BINARY-REDISTRIBUTABLE @EULA",
}

# Admin-account model (see docs / gesi-account-model): who can become root.
#   traditional     — root password set; wheel escalates via `su -`. No sudo.
#   sudo-augmented  — root password set AND a %wheel escalator rule. Both work.
#   rootless        — root LOCKED (passwd -l); first user escalates via sudo/doas.
ADMIN_MODELS: tuple[str, ...] = ("traditional", "sudo-augmented", "rootless")
ESCALATORS: tuple[str, ...] = ("sudo", "doas")


def license_accept_value(policy: str) -> str:
    """The ``ACCEPT_LICENSE`` string for a policy key; raises on an unknown rung."""
    try:
        return LICENSE_POLICIES[policy]
    except KeyError:
        raise ValueError(f"unknown license policy: {policy!r}") from None


def sets_root_password(admin_model: str) -> bool:
    """Whether this admin model sets a root password (rootless locks root instead)."""
    if admin_model not in ADMIN_MODELS:
        raise ValueError(f"unknown admin model: {admin_model!r}")
    return admin_model != "rootless"


def installs_escalator(admin_model: str) -> bool:
    """Whether this admin model installs+configures a sudo/doas escalator rule."""
    if admin_model not in ADMIN_MODELS:
        raise ValueError(f"unknown admin model: {admin_model!r}")
    return admin_model in ("sudo-augmented", "rootless")


@dataclass(slots=True, frozen=True)
class UserSpec:
    """The optional non-root user to create in the target."""

    name: str
    comment: str = ""
    shell: str = "/bin/bash"
    wheel: bool = True


@dataclass(slots=True, frozen=True)
class NetworkSpec:
    """The installed system's network choice (wired netifrc + DNS/hosts).

    Kept minimal here; the network step fills in the details when the registry is
    wired. ``dhcp`` false means a static ``address``/``gateway``.
    """

    dhcp: bool = True
    interface: str = ""
    address: str = ""
    gateway: str = ""
    nameservers: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class GpuSpec:
    """The target's GPU driver setup.

    ``video_cards`` are the ``VIDEO_CARDS`` tokens written to make.conf (e.g.
    ``("nvidia",)`` or ``("amdgpu", "radeonsi")``), typically auto-detected from
    ``lspci`` via ``hwflags.detect``. ``nvidia_proprietary`` requests the
    out-of-tree ``x11-drivers/nvidia-drivers`` stack — license acceptance, the
    kernel module, DRM modeset and a nouveau blacklist — rather than nouveau, which
    modern GeForce cards need for a working Wayland/HeDE desktop. The empty/``False``
    default is safe: firmware only, no GPU driver (what the stage3 ships stands).
    """

    video_cards: tuple[str, ...] = ()
    nvidia_proprietary: bool = False
    kernel_open: bool = False       # build nvidia-drivers with the OPEN kernel modules
    # (USE=kernel-open). NVIDIA-recommended for Turing+ (RTX 20-series and newer, incl.
    # Ada); NOT supported on pre-Turing cards, so it's off by default. Only meaningful
    # with nvidia_proprietary.
    nvidia_slot: str = ""           # nvidia-drivers SLOT for a legacy branch, e.g.
    # "0/470" (Kepler) or "0/390" (Fermi). Empty = the current/default slot. When set,
    # the driver atom is slotted and GeST writes a package.unmask (the legacy slots are
    # masked upstream). Only meaningful with nvidia_proprietary; kernel_open is never
    # set for a legacy slot.


@dataclass(slots=True, frozen=True)
class InstallPlan:
    """Everything one install needs, assembled and reviewed before execution."""

    disk: DiskPlan                 # the destructive layout (provision.uefi_plan)
    mount: MountPlan               # mount.derive_mount_plan(disk, root)
    stage3: Stage3Selection        # resolved tarball URL/size/digests/signature
    kernel: BuildConfig            # method / jobs / initramfs
    bootloader: InstallConfig      # firmware / efi_directory / boot_directory
    hostname: str
    timezone: str
    locale: str
    keymap: str
    arch: str = "amd64"            # target CPU arch: "amd64" | "arm64" (Asahi).
    # Derived from the chosen stage3 variant; the one arch-aware step (bootloader
    # → GRUB --target) branches on it. Disk/mount/kernel are arch-neutral.
    profile: str = "default/linux/amd64/23.0/systemd"   # eselect profile target
    # (a profile NAME, not a number — systemd for HeDE; assemble derives it per
    # arch + stage3 flavor via assemble.profile_name)
    root_password: bool = True     # whether to set it (secret prompted at run)
    user: UserSpec | None = None
    network: NetworkSpec = field(default_factory=NetworkSpec)
    binary_pref: bool = True       # --getbinpkg for @world, else source
    tier2: frozenset[str] = frozenset()   # opt-in day-2 modules, off by default
    desktop: bool = False          # install the HeDE desktop (gui-apps/hede + plymouth);
    # False = base Gentoo. GeSI sets it True. Gates the InstallDesktop step and, with
    # it, whether seamless boot can take effect (its plymouth/theme deps come from here).
    gpu: GpuSpec = field(default_factory=GpuSpec)   # VIDEO_CARDS + optional NVIDIA
    # proprietary stack; drives WriteMakeConf's VIDEO_CARDS and the InstallGpuDrivers
    # step. Default (empty) installs firmware only — no driver — a safe no-op.
    license: str = "full"          # ACCEPT_LICENSE policy rung (LICENSE_POLICIES key);
    # rendered into make.conf by WriteMakeConf. Full is the Desktop default.
    admin_model: str = "traditional"   # who can become root (ADMIN_MODELS); gates
    # SetRootPassword + the escalator step. Traditional = today's root+su behaviour.
    escalator: str = "sudo"        # sudo|doas — the escalator installed for
    # sudo-augmented/rootless models (ignored by traditional).
    global_use: tuple[str, ...] = ()   # system-wide USE= tokens resolved from the
    # wizard's Features checklist (capabilities.resolve_global_use); WriteMakeConf renders them.
    make_conf_overrides: tuple[tuple[str, str], ...] = ()   # Custom-role raw make.conf
    # var overrides (name, value); overlaid last by WriteMakeConf. Empty for canned roles.
