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

# The GRUB platform target per (arch, firmware) — the ``--target=`` value.
# amd64 UEFI/BIOS are the x86 defaults; arm64 UEFI is the Apple Silicon (Asahi)
# path, where GRUB runs as an EFI app under U-Boot. arm64 has no BIOS target.
_GRUB_TARGETS = {
    ("amd64", "uefi"): "x86_64-efi",
    ("amd64", "bios"): "i386-pc",
    ("arm64", "uefi"): "arm64-efi",
}


def grub_target(arch: str, firmware: str) -> str:
    """The GRUB ``--target=`` platform for ``arch``/``firmware`` (e.g. arm64+uefi
    → ``arm64-efi``). Raises on an unsupported combination (e.g. arm64 BIOS)."""
    try:
        return _GRUB_TARGETS[(arch, firmware)]
    except KeyError:
        raise ValueError(f"no GRUB target for arch={arch!r} firmware={firmware!r}") from None


def _valid_path(path: str) -> bool:
    return path.startswith("/") and "\n" not in path and "\0" not in path


def grub_mkconfig_argv(
    output: str = GRUB_CFG, *, grub_mkconfig: str = "grub-mkconfig"
) -> list[str]:
    if not _valid_path(output):
        raise ValueError(f"invalid output path: {output!r}")
    # Write via a shell stdout-redirect rather than grub-mkconfig's own ``-o``. Inside
    # the long-running installer, ``grub-mkconfig -o`` has produced a **0-byte**
    # grub.cfg — leaving a system that drops to the GRUB rescue prompt on boot —
    # even though the identical command run standalone always works; ``-o`` does its
    # own ``exec >tmp`` + rename, and that internal redirect is what comes up empty.
    # Redirecting stdout ourselves sidesteps it. Then: retry once, and only commit a
    # NON-empty result (``test -s``) — so an empty config fails the step loudly
    # instead of silently shipping an unbootable install (installer bug #13).
    tmp = f"{output}.gest-new"
    script = (f"{grub_mkconfig} >{tmp} 2>/dev/null; "
              f"test -s {tmp} || {grub_mkconfig} >{tmp} 2>/dev/null; "
              f"test -s {tmp} && mv -f {tmp} {output}")
    return ["sh", "-c", script]


def grub_install_argv(
    firmware: str,
    *,
    arch: str = "amd64",
    efi_directory: str = "/efi",
    bootloader_id: str = "GRUB",
    removable: bool = False,
    disk: str = "",
    boot_directory: str = "",
    grub_install: str = "grub-install",
) -> list[str]:
    """Build the `grub-install` argv for a UEFI or BIOS install.

    The ``--target`` platform is derived from ``arch``/``firmware`` (:func:`grub_target`)
    — amd64 UEFI is ``x86_64-efi``, arm64 UEFI (Apple Silicon/Asahi) is ``arm64-efi``.
    UEFI writes the loader into ``efi_directory`` (a mounted ESP) and registers an
    efibootmgr entry named ``bootloader_id``; ``removable`` also drops the
    fallback ``/EFI/BOOT/BOOT*.EFI``. BIOS writes boot code to ``disk``'s MBR.
    ``boot_directory`` (e.g. ``/mnt/gentoo/boot``) targets an install root other
    than the running system; empty means the live host's ``/boot``.
    """
    if firmware not in FIRMWARES:
        raise ValueError(f"unknown firmware: {firmware!r}")
    target = grub_target(arch, firmware)   # validates the (arch, firmware) pair
    argv = [grub_install]
    if firmware == "uefi":
        if not _valid_path(efi_directory):
            raise ValueError(f"invalid EFI directory: {efi_directory!r}")
        if not _ID_RE.match(bootloader_id):
            raise ValueError(f"invalid bootloader id: {bootloader_id!r}")
        argv += [f"--target={target}", f"--efi-directory={efi_directory}",
                 f"--bootloader-id={bootloader_id}"]
        if removable:
            argv.append("--removable")
    else:  # bios
        if not _DEVICE_RE.match(disk) or ".." in disk:
            raise ValueError(f"invalid target disk: {disk!r}")
        argv.append(f"--target={target}")
    if boot_directory:
        if not _valid_path(boot_directory):
            raise ValueError(f"invalid boot directory: {boot_directory!r}")
        argv.append(f"--boot-directory={boot_directory}")
    if firmware == "bios":
        argv.append(disk)          # positional target disk, last
    return argv
