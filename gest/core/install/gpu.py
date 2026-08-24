"""Pure command/config builders for installing GPU drivers + firmware into the
target — the GPU counterpart of :mod:`gest.core.install.desktop`.

Everything here is a pure value (paths, atom lists, config bodies) so the
``InstallGpuDrivers`` registry step stays thin and this is unit-testable without a
chroot. The step accepts the licenses these atoms need, emerges them into the
target, and (for NVIDIA) drops a modprobe.d file that enables DRM KMS and
blacklists nouveau — what a Wayland/HeDE desktop needs on a modern GeForce card.

See ``docs/design/installer-gpu.md`` for the full design (ordering, cmdline vs
modprobe.d, the framebuffer/boot flow, and the per-vendor matrix).
"""

from __future__ import annotations

import re

from gest.core.install.plan import GpuSpec

#: The ``package.license`` fragment GeST owns for GPU/firmware atoms (a file inside
#: the ``package.license/`` include dir, like desktop's ``package.accept_keywords``).
PACKAGE_LICENSE = "/etc/portage/package.license/gest-gpu"
#: modprobe.d drop-in enabling NVIDIA DRM KMS + blacklisting nouveau.
MODPROBE_CONF = "/etc/modprobe.d/gest-gpu.conf"
#: package.use fragment GeST owns for GPU atoms (e.g. nvidia-drivers[kernel-open]).
PACKAGE_USE = "/etc/portage/package.use/gest-gpu"
#: package.unmask fragment GeST owns — unmasks a legacy nvidia-drivers SLOT (0/470,
#: 0/390) which the Gentoo profile masks by default.
PACKAGE_UNMASK = "/etc/portage/package.unmask/gest-gpu"
#: package.accept_keywords fragment GeST owns for GPU/firmware atoms.
PACKAGE_ACCEPT_KEYWORDS = "/etc/portage/package.accept_keywords/gest-gpu"

#: linux-firmware carries NVIDIA GSP blobs + most Wi-Fi/other firmware; a fresh
#: stage3 ships none, so we always install it.
FIRMWARE_ATOM = "sys-kernel/linux-firmware"
#: The proprietary NVIDIA driver (out-of-tree kernel module + userspace).
NVIDIA_ATOM = "x11-drivers/nvidia-drivers"


def video_cards_value(gpu: GpuSpec) -> str:
    """The ``VIDEO_CARDS`` value for make.conf (space-joined), or ``""`` if none."""
    return " ".join(gpu.video_cards)


def nvidia_atom(gpu: GpuSpec) -> str:
    """The nvidia-drivers atom to emerge — slotted for a legacy branch (e.g.
    ``x11-drivers/nvidia-drivers:0/470`` for Kepler), bare for the current slot."""
    return f"{NVIDIA_ATOM}:{gpu.nvidia_slot}" if gpu.nvidia_slot else NVIDIA_ATOM


def driver_atoms(gpu: GpuSpec) -> list[str]:
    """Packages to emerge into the target: firmware always, ``nvidia-drivers`` when
    the proprietary stack is requested (slotted for a legacy Kepler/Fermi card).
    AMD/Intel need no extra package here — their kernel drivers are in-tree and mesa
    comes with @world/the desktop, keyed on the ``VIDEO_CARDS`` this plan writes to
    make.conf."""
    atoms = [FIRMWARE_ATOM]
    if gpu.nvidia_proprietary:
        atoms.append(nvidia_atom(gpu))
    return atoms


def package_accept_keywords(gpu: GpuSpec, arch: str) -> str:
    """The ``package.accept_keywords`` body for the GPU/firmware atoms.

    sys-kernel/linux-firmware's newest snapshots are ``~arch``, and a current
    nvidia-drivers pins a linux-firmware newer than the stable one (its GSP blobs
    need it) — so the firmware ends up masked at the GPU step and the emerge dies
    naming the live ``99999999`` ebuild. Accept ``~arch`` for firmware always, and
    for the nvidia driver atom when the proprietary stack is requested."""
    lines = [f"{FIRMWARE_ATOM} ~{arch}"]
    if gpu.nvidia_proprietary:
        lines.append(f"{nvidia_atom(gpu)} ~{arch}")
    return "".join(f"{line}\n" for line in lines)


def package_unmask(gpu: GpuSpec) -> str:
    """The ``package.unmask`` body needed to install a legacy NVIDIA branch, or
    ``""`` when none is. Gentoo's profile masks the legacy nvidia-drivers SLOTs
    (0/470 Kepler, 0/390 Fermi); without unmasking the chosen slot the emerge is
    mask-blocked. No-op for the current slot (unmasked) and for AMD/Intel/nouveau."""
    if gpu.nvidia_proprietary and gpu.nvidia_slot:
        return ("# Legacy NVIDIA driver slot — managed by GeST\n"
                f"{NVIDIA_ATOM}:{gpu.nvidia_slot}\n")
    return ""


def package_use(gpu: GpuSpec) -> str:
    """The ``package.use`` body for GPU atoms, or ``""`` when none is needed. Sets
    ``kernel-open`` on nvidia-drivers when the open kernel modules are requested
    (NVIDIA-recommended for Turing+/Ada). Meaningful only with the proprietary stack."""
    if gpu.nvidia_proprietary and gpu.kernel_open:
        return ("# GPU USE flags — managed by GeST\n"
                f"{NVIDIA_ATOM} kernel-open\n")
    return ""


def package_license(gpu: GpuSpec) -> str:
    """The ``package.license`` body accepting what the driver atoms need:
    ``linux-fw-redistributable`` for linux-firmware, and ``NVIDIA-r2`` for the
    proprietary driver (both outside the profile's default ACCEPT_LICENSE, so
    without this the emerge is license-masked)."""
    lines = [
        "# GPU driver + firmware licenses — managed by GeST",
        f"{FIRMWARE_ATOM} linux-fw-redistributable",
    ]
    if gpu.nvidia_proprietary:
        lines.append(f"{NVIDIA_ATOM} NVIDIA-r2")
    return "\n".join(lines) + "\n"


def modprobe_conf() -> str:
    """The NVIDIA modprobe drop-in: enable DRM KMS (``nvidia_drm.modeset=1`` — needed
    by wlroots/Wayland and the Plymouth splash) with the fbdev framebuffer, and
    blacklist nouveau so it can't bind the card first."""
    return (
        "# NVIDIA proprietary GPU — managed by GeST\n"
        "blacklist nouveau\n"
        "options nvidia_drm modeset=1 fbdev=1\n"
    )


#: Kernel cmdline args for the NVIDIA proprietary stack. The modprobe.d file above
#: only takes effect once the real root is mounted, but genkernel builds the
#: initramfs BEFORE the driver is installed — so without a cmdline blacklist nouveau
#: can still bind the card during early boot. These force the blacklist + DRM KMS
#: from the very first stage.
NVIDIA_CMDLINE = (
    "rd.driver.blacklist=nouveau modprobe.blacklist=nouveau "
    "nvidia_drm.modeset=1 nvidia_drm.fbdev=1"
)
#: The /etc/default/grub key the args merge into (applies to every boot entry).
GRUB_CMDLINE_KEY = "GRUB_CMDLINE_LINUX"


def kernel_cmdline(gpu: GpuSpec) -> str:
    """Extra kernel cmdline args this GPU needs — the nouveau-blacklist + modeset
    for the NVIDIA proprietary stack; ``""`` otherwise (in-kernel amdgpu/i915 need
    no cmdline coaxing)."""
    return NVIDIA_CMDLINE if gpu.nvidia_proprietary else ""


def apply_gpu_cmdline(existing: str, gpu: GpuSpec) -> str:
    """Merge :func:`kernel_cmdline` into ``GRUB_CMDLINE_LINUX`` in an
    ``/etc/default/grub`` body, appending (deduped) to any existing value and
    rewriting the line in place; appends the key if absent. Idempotent, and a no-op
    when the GPU needs no args — so re-running an install never doubles the args."""
    args = kernel_cmdline(gpu)
    if not args:
        return existing
    want = args.split()
    key_re = re.compile(rf'^\s*#?\s*{GRUB_CMDLINE_KEY}=(?:"(.*)"|(.*))\s*$')
    lines = existing.split("\n")
    for i, line in enumerate(lines):
        m = key_re.match(line)
        if m:
            cur = (m.group(1) if m.group(1) is not None else m.group(2)).split()
            merged = cur + [a for a in want if a not in cur]
            lines[i] = f'{GRUB_CMDLINE_KEY}="{" ".join(merged)}"'
            return "\n".join(lines)
    if lines and lines[-1].strip():
        lines.append("")
    lines.append("# GPU cmdline — managed by GeST")
    lines.append(f'{GRUB_CMDLINE_KEY}="{" ".join(want)}"')
    return "\n".join(lines)
