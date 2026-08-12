"""Pure, validated argv builders for the bootloader module.

Config regeneration (`grub-mkconfig`) and installation (`grub-install`, UEFI or
BIOS). Both end up running as root, so every path/id/device is validated here
before it can reach a shell; the builders are pure so they're CI-testable.
"""

from __future__ import annotations

import re

from gest.core.bootloader.reader import GRUB_CFG

# A GRUB EFI bootloader id (the /EFI/<id>/ dir and the efibootmgr entry name).
_ID_RE = re.compile(r"\A[A-Za-z0-9_-]{1,32}\Z")
# The whole-disk node a BIOS install writes its boot code to.
_DEVICE_RE = re.compile(r"\A/dev/[A-Za-z0-9][A-Za-z0-9/_-]*\Z")

FIRMWARES = frozenset({"uefi", "bios"})


def _valid_path(path: str) -> bool:
    return path.startswith("/") and "\n" not in path and "\0" not in path


def grub_mkconfig_argv(
    output: str = GRUB_CFG, *, grub_mkconfig: str = "grub-mkconfig"
) -> list[str]:
    if not _valid_path(output):
        raise ValueError(f"invalid output path: {output!r}")
    return [grub_mkconfig, "-o", output]


def grub_install_argv(
    firmware: str,
    *,
    efi_directory: str = "/efi",
    bootloader_id: str = "GRUB",
    removable: bool = False,
    disk: str = "",
    boot_directory: str = "",
    grub_install: str = "grub-install",
) -> list[str]:
    """Build the `grub-install` argv for a UEFI or BIOS install.

    UEFI writes the loader into ``efi_directory`` (a mounted ESP) and registers an
    efibootmgr entry named ``bootloader_id``; ``removable`` also drops the
    fallback ``/EFI/BOOT/BOOTX64.EFI``. BIOS writes boot code to ``disk``'s MBR.
    ``boot_directory`` (e.g. ``/mnt/gentoo/boot``) targets an install root other
    than the running system; empty means the live host's ``/boot``.
    """
    if firmware not in FIRMWARES:
        raise ValueError(f"unknown firmware: {firmware!r}")
    argv = [grub_install]
    if firmware == "uefi":
        if not _valid_path(efi_directory):
            raise ValueError(f"invalid EFI directory: {efi_directory!r}")
        if not _ID_RE.match(bootloader_id):
            raise ValueError(f"invalid bootloader id: {bootloader_id!r}")
        argv += ["--target=x86_64-efi", f"--efi-directory={efi_directory}",
                 f"--bootloader-id={bootloader_id}"]
        if removable:
            argv.append("--removable")
    else:  # bios
        if not _DEVICE_RE.match(disk) or ".." in disk:
            raise ValueError(f"invalid target disk: {disk!r}")
        argv.append("--target=i386-pc")
    if boot_directory:
        if not _valid_path(boot_directory):
            raise ValueError(f"invalid boot directory: {boot_directory!r}")
        argv.append(f"--boot-directory={boot_directory}")
    if firmware == "bios":
        argv.append(disk)          # positional target disk, last
    return argv
