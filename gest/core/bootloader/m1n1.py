"""Pure argv builder for the Apple Silicon (Asahi) m1n1 boot stub.

On Apple Silicon the boot chain is Apple iBoot → **m1n1** → U-Boot → GRUB (EFI) →
kernel. GRUB is installed as ``arm64-efi`` (see ``bootloader/commands.py``); this
module handles the stage *before* GRUB — the m1n1 + U-Boot payload that Asahi's
``asahi-scripts`` builds and writes with ``update-m1n1``.

Pure and CI-testable: it only shapes the ``update-m1n1`` argv (validated paths).
The exact tool behaviour comes from ``asahi-scripts`` on the target; ``update-m1n1``
reads ``/etc/default/m1n1`` and, given an output path, writes the combined
``boot.bin`` there — conventionally ``<ESP>/m1n1/boot.bin``. Running it is the job of
the install step; there is no amd64 analogue, so the step no-ops off Apple Silicon.
"""

from __future__ import annotations


def default_boot_bin(efi_directory: str) -> str:
    """The conventional m1n1 payload path on the mounted ESP (``<ESP>/m1n1/boot.bin``)."""
    return f"{efi_directory.rstrip('/')}/m1n1/boot.bin"


def _valid_path(path: str) -> bool:
    return path.startswith("/") and "\n" not in path and "\0" not in path and ".." not in path


def update_m1n1_argv(boot_bin: str = "", *, update_m1n1: str = "update-m1n1") -> list[str]:
    """Build the ``update-m1n1`` argv that (re)writes the m1n1 + U-Boot boot payload.

    With ``boot_bin`` empty, ``update-m1n1`` uses its configured target
    (``/etc/default/m1n1``); given a path, it writes the payload there. The path is
    validated (absolute, no newline/NUL, no ``..``) since this runs as root.
    """
    if not boot_bin:
        return [update_m1n1]
    if not _valid_path(boot_bin):
        raise ValueError(f"invalid m1n1 boot path: {boot_bin!r}")
    return [update_m1n1, boot_bin]
