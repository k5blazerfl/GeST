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
from gest.core.hwflags import detect as hwdetect
from gest.core.install import capabilities
from gest.core.install.plan import (
    ADMIN_MODELS,
    CLOCK_MODES,
    ESCALATORS,
    LICENSE_POLICIES,
    GpuSpec,
    InstallPlan,
    NetworkSpec,
    UserSpec,
    sets_root_password,
)
from gest.core.kernel import config as kconfig
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
    # Split /home onto its own partition: root takes root_size, /home takes the rest.
    separate_home: bool = False
    root_size: str = "40G"            # fixed root size when separate_home (else root=rest)
    home_fs: str = "ext4"
    target_root: str = DEFAULT_TARGET_ROOT
    # stage3
    variant: Stage3Variant = DEFAULT_VARIANT
    # system (editable rows in 5b; defaults keep a fresh overview valid)
    hostname: str = "gentoo"
    timezone: str = "America/New_York"   # US Eastern — the project's home (Tallahassee, FL)
    # and primary audience. Any zone is a searchable pick away; UTC is not a friendlier
    # default for the people most likely to use this.
    locale: str = "C.UTF-8"   # stays C.UTF-8 (glibc built-in, no locale-gen) until the
    # SetTimezoneLocale locale-gen fix lands; only then is en_US.UTF-8 safe as a default.
    keymap: str = "us"
    clock: str = "chrony"             # how the target keeps time (plan.CLOCK_MODES)
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
    kernel_method: str = "genkernel"  # "genkernel" (auto-config source build) | "make"
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
    # GPU: VIDEO_CARDS tokens for the target + whether to install the NVIDIA
    # proprietary stack. Empty/False = firmware only (safe). The UI populates these
    # from `resolve_gpu()` (lspci auto-detect); left unset, an install just skips the
    # driver. `nvidia_proprietary` implies a `nvidia` VIDEO_CARDS token (added in
    # assembly), so a detected GeForce card gets a working Wayland/HeDE desktop.
    video_cards: tuple[str, ...] = ()
    nvidia_proprietary: bool = False
    kernel_open: bool = False           # nvidia-drivers[kernel-open] (Turing+/Ada)
    nvidia_slot: str = ""               # legacy nvidia-drivers SLOT (0/470, 0/390);
    # empty = current slot. Set by resolve_gpu() for a detected Kepler/Fermi card.
    gpu_auto: bool = True               # auto-detect the GPU (lspci) at install time;
    # False = the user overrode it in the UI, so video_cards/nvidia_proprietary are
    # taken as-is (including an explicit "none" = empty). Not a plan field (UI-only).
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
    # --- wizard fields (the YaST-gated redesign) ------------------------------
    # System Role drives the proposal (assemble.propose); "custom" makes every
    # field user-editable. The bare defaults below are the Desktop shape; propose()
    # is the authoritative per-role setter the wizard calls when a role is picked.
    role: str = "desktop"             # desktop | server | minimal | custom
    license: str = "full"             # ACCEPT_LICENSE rung (plan.LICENSE_POLICIES key)
    # Features checklist → system-wide USE (capabilities keys). Desktop pre-checks
    # the common ones; resolve_global_use turns this into the make.conf USE tokens.
    capabilities: set[str] = field(
        default_factory=lambda: {"bluetooth", "printing", "wifi", "audio",
                                 "wayland", "vaapi", "codecs"})
    admin_model: str = "traditional"  # plan.ADMIN_MODELS: who can become root
    escalator: str = "sudo"           # sudo | doas (sudo-augmented / rootless)
    # Custom-role raw make.conf overrides (var -> value), overlaid last. Empty otherwise.
    make_conf_overrides: dict[str, str] = field(default_factory=dict)


ROLES: tuple[str, ...] = ("desktop", "server", "minimal", "custom")

# Common desktop Features (capability keys) the Desktop role pre-checks.
_DESKTOP_CAPABILITIES = frozenset(
    {"bluetooth", "printing", "wifi", "audio", "wayland", "vaapi", "codecs"})


def propose(role: str) -> InstallSelections:
    """Role-proposed selections — the wizard's "proposals over blank fields".

    A System Role fills the role-*owned* fields (stage3 flavor via desktop-ness,
    build strategy, GPU policy, license, admin model, day-2 modules, Features)
    with a coherent default set; everything else (disk, hostname, tz/locale, user,
    root pw) is identical across roles and stays as the bare defaults. ``custom``
    returns the Desktop baseline with every field left editable. Raises on an
    unknown role. Pure — the wizard calls this when the role gate is answered and
    then lets later gates diff against it (the ``•changed`` markers in review).
    """
    if role not in ROLES:
        raise ValueError(f"unknown role: {role!r}")
    sel = InstallSelections(role=role)
    if role == "desktop":
        sel.install_desktop = True
        sel.gpu_auto = True
        sel.binary_pref = True
        sel.seamless = True
        sel.license = "full"                 # @B-R @EULA — everything, no reconcile
        sel.admin_model = "rootless"         # Ubuntu-familiar for refugees
        sel.escalator = "sudo"
        sel.tier2 = set()
        sel.capabilities = set(_DESKTOP_CAPABILITIES)
    elif role == "server":
        sel.install_desktop = False
        sel.gpu_auto = False                 # firmware only, no desktop GPU driver
        sel.binary_pref = True
        sel.seamless = False
        sel.license = "redistributable"      # @B-R — firmware+NVIDIA-r2, no EULA
        sel.admin_model = "traditional"      # root + su, the operator's model
        sel.tier2 = {"sshd", "firewall"}
        sel.capabilities = set()
    elif role == "minimal":
        sel.install_desktop = False
        sel.gpu_auto = False
        sel.binary_pref = False              # compile from source (tuned, small base)
        sel.seamless = False
        sel.license = "redistributable"
        sel.admin_model = "traditional"
        sel.tier2 = set()
        sel.capabilities = set()
    # custom: the InstallSelections(role="custom") baseline (Desktop shape), all
    # fields editable downstream — no overrides here.
    return sel


# The fields a System Role owns — everything else (disk, hostname, tz/locale,
# user, root pw) is identical across roles and must survive a role change.
_ROLE_OWNED = (
    "role", "install_desktop", "gpu_auto", "binary_pref", "seamless",
    "license", "admin_model", "escalator", "tier2", "capabilities",
    "video_cards", "nvidia_proprietary",
)


def apply_role(sel: InstallSelections, role: str) -> None:
    """Re-apply a role's proposal onto an existing selection, in place.

    Only the role-owned fields change; user-entered disk/localization/account
    values are preserved. Lets the wizard's System Role gate switch roles without
    wiping earlier gates. Raises on an unknown role (via :func:`propose`).
    """
    proposed = propose(role)
    for attr in _ROLE_OWNED:
        setattr(sel, attr, getattr(proposed, attr))


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


def _build_gpu(sel: InstallSelections) -> GpuSpec:
    """The target's GPU setup from the selections (pure).

    ``nvidia_proprietary`` implies a ``nvidia`` VIDEO_CARDS token, so requesting the
    proprietary stack alone is enough — assembly adds the token if the caller didn't.
    """
    cards = tuple(sel.video_cards)
    if sel.nvidia_proprietary and "nvidia" not in cards:
        cards = (*cards, "nvidia")
    slot = sel.nvidia_slot if sel.nvidia_proprietary else ""
    return GpuSpec(video_cards=cards, nvidia_proprietary=sel.nvidia_proprietary,
                   kernel_open=sel.kernel_open and sel.nvidia_proprietary and not slot,
                   nvidia_slot=slot)


def resolve_gpu(runner: hwdetect.Runner | None = None) -> GpuSpec:
    """Auto-detect the GPU from ``lspci`` (I/O — the GPU peer of ``resolve_stage3``).

    Returns a :class:`GpuSpec` with the detected VIDEO_CARDS tokens, opting into the
    NVIDIA proprietary stack when an NVIDIA card is present (nouveau can't drive a
    modern GeForce under Wayland/HeDE), and into the OPEN kernel modules when the
    card is Turing-or-newer (NVIDIA-recommended, and it sidesteps closed-module IBT
    issues). The UI calls this to populate the selections before assembly; empty on a
    host with no detectable GPU (or no ``lspci``).
    """
    run = runner or hwdetect._default_runner
    try:
        rc, out = run(["lspci"])
    except OSError:                      # missing binary (ENOENT) OR an exec/IO error (EIO)
        return GpuSpec()                 # firmware-only — never fail the whole prep on lspci
    if rc != 0:
        return GpuSpec()
    cards = hwdetect.parse_video_cards(out)

    # AMD: swap the default amdgpu tokens for the radeon backends on a pre-GCN card.
    if "amdgpu" in cards and hwdetect.amd_legacy_radeon(out):
        cards = [c for c in cards if c not in ("amdgpu", "radeonsi")]
        for tok in hwdetect._AMD_LEGACY_TOKENS:
            if tok not in cards:
                cards.append(tok)

    # NVIDIA: pick the proprietary driver branch by GPU architecture.
    branch = hwdetect.nvidia_driver_branch(out)
    if branch == "nouveau":
        # Tesla-and-older: no supported proprietary driver → nouveau (open, in-tree).
        cards = [c for c in cards if c != "nvidia"]
        if "nouveau" not in cards:
            cards.append("nouveau")
        return GpuSpec(video_cards=tuple(cards))
    if branch in ("legacy-470", "legacy-390"):
        return GpuSpec(video_cards=tuple(cards), nvidia_proprietary=True,
                       nvidia_slot=hwdetect.NVIDIA_SLOTS[branch])
    if branch == "current":
        return GpuSpec(video_cards=tuple(cards), nvidia_proprietary=True,
                       kernel_open=hwdetect.nvidia_open_recommended(out))
    # No NVIDIA GPU: AMD/Intel/none — firmware + VIDEO_CARDS only.
    return GpuSpec(video_cards=tuple(cards))


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


# The current Gentoo profile line. `default/linux/<arch>/23.0` is the OpenRC/base
# profile; its `/systemd` child is the systemd one. Selecting by name (not eselect
# number, which is unstable) so the target keeps the init its stage3 shipped.
PROFILE_VERSION = "23.0"


def profile_name(arch: str, flavor: str) -> str:
    """The ``eselect profile`` target for ``arch`` + stage3 ``flavor``. A systemd
    stage3 (flavor ends in ``systemd``) → the ``/systemd`` profile so USE=systemd
    etc. stay set; OpenRC flavors → the base ``23.0`` profile."""
    base = f"default/linux/{arch}/{PROFILE_VERSION}"
    return f"{base}/systemd" if flavor.endswith("systemd") else base


def _dev_path(name: str) -> str:
    """A ``/dev`` node from a bare disk name (``vda`` -> ``/dev/vda``); an
    already-absolute ``/dev/...`` path passes through unchanged."""
    name = name.strip()
    return name if name.startswith("/dev/") else f"/dev/{name}"


def assemble_plan(sel: InstallSelections, stage3: Stage3Selection) -> InstallPlan:
    """Build the frozen :class:`InstallPlan` from ``sel`` and a resolved ``stage3``.

    Pure: no I/O. Raises ``ValueError`` on a selection the module validators reject
    (empty disk, bad filesystem/size, empty root password, bad firmware, a bad
    hostname/timezone/locale/keymap, an invalid user name, or a bad target-network
    address/gateway/nameserver).
    """
    if not sel.disk:
        raise ValueError("no target disk selected")
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
    if sel.license not in LICENSE_POLICIES:
        raise ValueError(f"invalid license policy: {sel.license!r}")
    if sel.admin_model not in ADMIN_MODELS:
        raise ValueError(f"invalid admin model: {sel.admin_model!r}")
    if sel.escalator not in ESCALATORS:
        raise ValueError(f"invalid escalator: {sel.escalator!r}")
    if sel.clock not in CLOCK_MODES:
        raise ValueError(f"invalid clock mode: {sel.clock!r}")
    # Admin-model safety: traditional/sudo-augmented need a root password; rootless
    # locks root, so it instead needs an admin-capable (wheel) user to escalate from
    # — never ship a system you can't administer (gesi-account-model invariant).
    if sets_root_password(sel.admin_model):
        if not sel.root_password:
            raise ValueError("a root password is required")
    elif not (sel.create_user and valid_user_name(sel.user_name) and sel.user_wheel):
        raise ValueError("a rootless install needs an admin-capable (wheel) user")
    global_use = capabilities.resolve_global_use(sel.capabilities)  # raises on typo
    overrides = tuple(sorted(sel.make_conf_overrides.items()))
    user = _build_user(sel)
    network = _build_network(sel)
    # Seamless boot needs plymouth + the HeDE theme, both installed by the desktop
    # step; requesting it without the desktop is a no-op, not a broken install.
    use_seamless = sel.seamless and sel.install_desktop
    profile = profile_name(arch, sel.variant.flavor)
    # BIOS installs need a GPT layout with a BIOS-boot partition (no ESP); UEFI
    # needs the ESP. The bootloader step branches on firmware to match this layout.
    home_fs = sel.home_fs if sel.separate_home else None
    root_size = sel.root_size if sel.separate_home else "rest"
    if sel.firmware == "bios":
        disk = provision.bios_plan(sel.disk, sel.swap_size, sel.root_fs,
                                   root_size=root_size, home_fs=home_fs)
    else:
        disk = provision.uefi_plan(sel.disk, sel.esp_size, sel.swap_size, sel.root_fs,
                                   root_size=root_size, home_fs=home_fs)
    mount = disk_mount.derive_mount_plan(disk, sel.target_root)
    return InstallPlan(
        disk=disk,
        mount=mount,
        stage3=stage3,
        # Seamless boot only takes effect when the desktop is installed — that's what
        # provides plymouth + the HeDE theme the genkernel/GRUB steps need.
        kernel=BuildConfig(
            method=sel.kernel_method, jobs=sel.kernel_jobs,
            initramfs=sel.kernel_initramfs, plymouth=use_seamless,
            # genkernel's default config lacks virtio etc., so a VM install can't
            # find its root disk. Point it at the curated per-arch config the
            # installer ships (staged into the target by StageKernelConfig) when
            # one exists for this arch; else fall back to genkernel's default.
            kernel_config=(kconfig.TARGET_KERNEL_CONFIG
                           if sel.kernel_method == "genkernel"
                           and kconfig.bundled_config(arch) is not None else "")),
        bootloader=InstallConfig(
            firmware=sel.firmware, efi_directory=sel.efi_directory,
            # BIOS GRUB writes to the target disk's /dev node. GeST stores disk names
            # bare ("vda"), but grub-install needs the device path, so normalise here
            # (as provision does for the layout) and default to the install disk when
            # no separate BIOS target was chosen. UEFI ignores this field.
            disk=(_dev_path(sel.boot_disk or sel.disk)
                  if sel.firmware == "bios" else sel.boot_disk),
            # The bootloader step runs chrooted into the target (native paths),
            # so seamless writes/stages inside the target with root="" — the chroot
            # is the seam. (plymouth is baked into the initramfs by BuildKernel above.)
            seamless=use_seamless),
        desktop=sel.install_desktop,
        gpu=_build_gpu(sel),
        profile=profile,
        arch=arch,
        hostname=sel.hostname,
        timezone=sel.timezone,
        locale=sel.locale,
        keymap=sel.keymap,
        clock=sel.clock,
        user=user,
        network=network,
        binary_pref=sel.binary_pref,
        tier2=frozenset(sel.tier2),
        # rootless locks root instead of setting a password (the escalator step + a
        # wheel user carry admin rights); traditional/sudo-augmented set it.
        root_password=sets_root_password(sel.admin_model),
        license=sel.license,
        admin_model=sel.admin_model,
        escalator=sel.escalator,
        global_use=global_use,
        make_conf_overrides=overrides,
    )
