"""Read kernel + bootloader state (unprivileged)."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

GRUB_CFG = "/boot/grub/grub.cfg"


@dataclass(slots=True)
class BootInfo:
    running_kernel: str = ""
    kernel_source: str = ""       # /usr/src/linux target
    bootloader: str = "unknown"   # grub / systemd-boot / unknown
    grub_cfg: str = GRUB_CFG
    kernels: list[str] = field(default_factory=list)  # installed /boot kernels


def parse_boot_kernels(names: list[str]) -> list[str]:
    """Kernel versions from /boot entries (vmlinuz-* / kernel-*), newest first."""
    versions: set[str] = set()
    for name in names:
        for prefix in ("vmlinuz-", "kernel-"):
            if name.startswith(prefix):
                versions.add(name[len(prefix):])
    return sorted(versions, reverse=True)


def running_kernel() -> str:
    return os.uname().release


def kernel_source(path: str = "/usr/src/linux") -> str:
    try:
        return os.path.basename(os.readlink(path))
    except OSError:
        return ""


def installed_kernels(boot: str = "/boot") -> list[str]:
    try:
        return parse_boot_kernels(os.listdir(boot))
    except OSError:
        return []


def detect_bootloader() -> str:
    if shutil.which("grub-mkconfig") and os.path.isdir("/boot/grub"):
        return "grub"
    if shutil.which("bootctl") and os.path.isdir("/boot/loader"):
        return "systemd-boot"
    return "unknown"


def boot_info() -> BootInfo:
    return BootInfo(
        running_kernel=running_kernel(),
        kernel_source=kernel_source(),
        bootloader=detect_bootloader(),
        kernels=installed_kernels(),
    )
