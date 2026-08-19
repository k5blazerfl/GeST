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
