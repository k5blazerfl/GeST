"""Pure command/config builders for installing GPU drivers + firmware into the
target — the GPU counterpart of :mod:`gest.core.install.desktop`.

Everything here is a pure value (paths, atom lists, config bodies) so the
``InstallGpuDrivers`` registry step stays thin and this is unit-testable without a
chroot. The step accepts the licenses these atoms need, emerges them into the
target, and (for NVIDIA) drops a modprobe.d file that enables DRM KMS and
blacklists nouveau — what a Wayland/HeDE desktop needs on a modern GeForce card.
"""

from __future__ import annotations

from gest.core.install.plan import GpuSpec

#: The ``package.license`` fragment GeST owns for GPU/firmware atoms (a file inside
#: the ``package.license/`` include dir, like desktop's ``package.accept_keywords``).
PACKAGE_LICENSE = "/etc/portage/package.license/gest-gpu"
#: modprobe.d drop-in enabling NVIDIA DRM KMS + blacklisting nouveau.
MODPROBE_CONF = "/etc/modprobe.d/gest-gpu.conf"

#: linux-firmware carries NVIDIA GSP blobs + most Wi-Fi/other firmware; a fresh
#: stage3 ships none, so we always install it.
FIRMWARE_ATOM = "sys-kernel/linux-firmware"
#: The proprietary NVIDIA driver (out-of-tree kernel module + userspace).
NVIDIA_ATOM = "x11-drivers/nvidia-drivers"


def video_cards_value(gpu: GpuSpec) -> str:
    """The ``VIDEO_CARDS`` value for make.conf (space-joined), or ``""`` if none."""
    return " ".join(gpu.video_cards)


def driver_atoms(gpu: GpuSpec) -> list[str]:
    """Packages to emerge into the target: firmware always, ``nvidia-drivers`` when
    the proprietary stack is requested. AMD/Intel need no extra package here — their
    kernel drivers are in-tree and mesa comes with @world/the desktop, keyed on the
    ``VIDEO_CARDS`` this plan writes to make.conf."""
    atoms = [FIRMWARE_ATOM]
    if gpu.nvidia_proprietary:
        atoms.append(NVIDIA_ATOM)
    return atoms


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
