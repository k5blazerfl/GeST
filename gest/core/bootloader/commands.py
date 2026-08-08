"""Pure, validated argv builder for bootloader-config regeneration."""

from __future__ import annotations

from gest.core.bootloader.reader import GRUB_CFG


def grub_mkconfig_argv(
    output: str = GRUB_CFG, *, grub_mkconfig: str = "grub-mkconfig"
) -> list[str]:
    if not output.startswith("/") or "\n" in output or "\0" in output:
        raise ValueError(f"invalid output path: {output!r}")
    return [grub_mkconfig, "-o", output]
