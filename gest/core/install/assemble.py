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

from dataclasses import dataclass, field

from gest.core.bootloader.install import InstallConfig
from gest.core.disk import mount as disk_mount
from gest.core.disk import provision
from gest.core.install.plan import InstallPlan, NetworkSpec, UserSpec
from gest.core.kernel.build import BuildConfig
from gest.core.network import netifrc, resolv
from gest.core.stage3 import index
from gest.core.stage3.model import (
    ARM64_ARCH,
    DEFAULT_VARIANT,
    SUPPORTED_ARCHES,
    Stage3Selection,
    Stage3Variant,
)
from gest.core.system.console import valid_keymap
from gest.core.system.hostname import valid_hostname
from gest.core.system.locale import valid_locale
from gest.core.system.timezone import valid_zone_name
from gest.core.users.commands import valid_name as valid_user_name

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
    # system (editable rows in 5b; defaults keep a fresh overview valid)
    hostname: str = "gentoo"
    timezone: str = "UTC"
    locale: str = "C.UTF-8"
    keymap: str = "us"
    # user (optional; created in the target when create_user)
    create_user: bool = False
    user_name: str = ""
    user_comment: str = ""
    user_shell: str = "/bin/bash"
    user_wheel: bool = True
    # target network (the INSTALLED system's netifrc/DNS — not the live env).
    # net_interface blank leaves it default/unconfigured (the step no-ops).
    net_interface: str = ""
    net_dhcp: bool = True
    net_address: str = ""             # CIDR, e.g. "192.168.1.5/24" (static only)
    net_gateway: str = ""             # default gateway IP (static only)
    net_nameservers: tuple[str, ...] = ()
    # kernel
    kernel_method: str = "make"       # "make" | "genkernel"
    kernel_jobs: int = 0              # 0 → the module resolves to CPU count
    kernel_initramfs: bool = True
    # bootloader
    firmware: str = "uefi"            # "uefi" | "bios"
    efi_directory: str = "/efi"
    boot_disk: str = ""               # BIOS target disk (firmware == "bios")
    # Install the HeDE desktop (gui-apps/hede + sys-boot/plymouth) into the target.
    # On by default — GeSI installs HeDE. The ProvisionDesktop step makes this work
    # offline (quickpkg the live env + seed the Amphitheater overlay); turn off for
    # a base-Gentoo install. See docs/design/desktop-provisioning.md.
    install_desktop: bool = True
    # Seamless graphical boot (GRUB Harbor theme + Plymouth splash in the initramfs).
    # Its plymouth/theme deps come from the desktop, so it only takes EFFECT when
    # install_desktop is also on (see assemble_plan) — the desktop gate is what keeps
    # it safe, so this stays True (the intent) rather than tracking the gate.
    seamless: bool = True
    # secret + toggles
    root_password: str = ""           # in-memory only; never in the plan
    binary_pref: bool = True          # --getbinpkg for @world
    # opt-in day-2 modules to set up during install (sshd/firewall/sudo/sysctl);
    # empty by default. See registry.TIER2_MODULES.
    tier2: set[str] = field(default_factory=set)


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


def _build_user(sel: InstallSelections) -> UserSpec | None:
    """The optional non-root user (``None`` unless ``create_user``).

    Reuses the shadow-utils name rule from ``users.commands`` — an empty or
    otherwise invalid name raises rather than assembling a bad plan.
    """
    if not sel.create_user:
        return None
    if not valid_user_name(sel.user_name):
        raise ValueError(f"invalid user name: {sel.user_name!r}")
    return UserSpec(
        name=sel.user_name,
        comment=sel.user_comment,
        shell=sel.user_shell,
        wheel=sel.user_wheel,
    )


def _build_network(sel: InstallSelections) -> NetworkSpec:
    """The installed system's netifrc/DNS choice.

    A blank interface means "leave it default" — the ConfigureNetwork step no-ops,
    so we return a default :class:`NetworkSpec`. When an interface is named, a
    static config's address/gateway are validated with the netifrc validators and
    every nameserver with the resolv validator; a bad value raises.
    """
    if not sel.net_interface:
        return NetworkSpec()
    if not sel.net_dhcp:
        if not netifrc.valid_address(sel.net_address):
            raise ValueError(f"invalid static address: {sel.net_address!r}")
        if not netifrc.valid_gateway(sel.net_gateway):
            raise ValueError(f"invalid gateway: {sel.net_gateway!r}")
    for ns in sel.net_nameservers:
        if not resolv.valid_nameserver(ns):
            raise ValueError(f"invalid nameserver: {ns!r}")
    return NetworkSpec(
        dhcp=sel.net_dhcp,
        interface=sel.net_interface,
        address=sel.net_address,
        gateway=sel.net_gateway,
        nameservers=tuple(sel.net_nameservers),
    )


def assemble_plan(sel: InstallSelections, stage3: Stage3Selection) -> InstallPlan:
    """Build the frozen :class:`InstallPlan` from ``sel`` and a resolved ``stage3``.

    Pure: no I/O. Raises ``ValueError`` on a selection the module validators reject
    (empty disk, bad filesystem/size, empty root password, bad firmware, a bad
    hostname/timezone/locale/keymap, an invalid user name, or a bad target-network
    address/gateway/nameserver).
    """
    if not sel.disk:
        raise ValueError("no target disk selected")
    if not sel.root_password:
        raise ValueError("a root password is required")
    if sel.firmware not in ("uefi", "bios"):
        raise ValueError(f"invalid firmware: {sel.firmware!r}")
    # Target arch flows from the chosen stage3 variant; the bootloader step branches
    # on it (GRUB --target). arm64 (Apple Silicon/Asahi) is UEFI-only — no BIOS GRUB.
    arch = sel.variant.arch
    if arch not in SUPPORTED_ARCHES:
        raise ValueError(f"unsupported target arch: {arch!r}")
    if arch == ARM64_ARCH and sel.firmware != "uefi":
        raise ValueError("arm64 installs are UEFI-only (no BIOS GRUB target)")
    if not valid_hostname(sel.hostname):
        raise ValueError(f"invalid hostname: {sel.hostname!r}")
    if not valid_zone_name(sel.timezone):
        raise ValueError(f"invalid timezone: {sel.timezone!r}")
    if not valid_locale(sel.locale):
        raise ValueError(f"invalid locale: {sel.locale!r}")
    if not valid_keymap(sel.keymap):
        raise ValueError(f"invalid keymap: {sel.keymap!r}")
    user = _build_user(sel)
    network = _build_network(sel)
    # Seamless boot needs plymouth + the HeDE theme, both installed by the desktop
    # step; requesting it without the desktop is a no-op, not a broken install.
    use_seamless = sel.seamless and sel.install_desktop
    disk = provision.uefi_plan(sel.disk, sel.esp_size, sel.swap_size, sel.root_fs)
    mount = disk_mount.derive_mount_plan(disk, sel.target_root)
    return InstallPlan(
        disk=disk,
        mount=mount,
        stage3=stage3,
        # Seamless boot only takes effect when the desktop is installed — that's what
        # provides plymouth + the HeDE theme the genkernel/GRUB steps need.
        kernel=BuildConfig(
            method=sel.kernel_method, jobs=sel.kernel_jobs,
            initramfs=sel.kernel_initramfs, plymouth=use_seamless),
        bootloader=InstallConfig(
            firmware=sel.firmware, efi_directory=sel.efi_directory, disk=sel.boot_disk,
            # The bootloader step runs chrooted into the target (native paths),
            # so seamless writes/stages inside the target with root="" — the chroot
            # is the seam. (plymouth is baked into the initramfs by BuildKernel above.)
            seamless=use_seamless),
        desktop=sel.install_desktop,
        arch=arch,
        hostname=sel.hostname,
        timezone=sel.timezone,
        locale=sel.locale,
        keymap=sel.keymap,
        user=user,
        network=network,
        binary_pref=sel.binary_pref,
        tier2=frozenset(sel.tier2),
    )
