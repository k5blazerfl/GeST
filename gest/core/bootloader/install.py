"""Install a bootloader (GRUB) and refresh its config — direct or via backend.

`InstallConfig` describes a UEFI or BIOS GRUB install; `install_steps` turns it
into the ordered pipeline (`grub-install` then, optionally, `grub-mkconfig`).
Both apply paths run the *same* two phases so the UI is identical either way:

* `install` — direct/in-process (live CD running as root), via an `Executor`.
* `install_via_backend` — the polkit-gated `BootloaderBackend` on an installed
  system, which re-validates and runs each phase as root.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from gest.core.bootloader import commands
from gest.core.exec.executor import Executor
from gest.core.exec.runner import OnProgress
from gest.core.exec.steps import Step, fail, run_steps


@dataclass(slots=True, frozen=True)
class InstallConfig:
    """A GRUB install request. ``regenerate`` also runs grub-mkconfig after."""

    firmware: str                    # "uefi" | "bios"
    efi_directory: str = "/efi"
    bootloader_id: str = "GRUB"
    removable: bool = False
    disk: str = ""                   # BIOS target disk
    boot_directory: str = ""         # install-root seam; empty = live host /boot
    regenerate: bool = True


def install_steps(config: InstallConfig) -> list[Step]:
    """The ordered pipeline: install GRUB, then (optionally) regenerate its config."""
    steps = [Step(
        f"install GRUB ({config.firmware})",
        commands.grub_install_argv(
            config.firmware,
            efi_directory=config.efi_directory,
            bootloader_id=config.bootloader_id,
            removable=config.removable,
            disk=config.disk,
            boot_directory=config.boot_directory,
        ),
    )]
    if config.regenerate:
        steps.append(Step("regenerate grub.cfg", commands.grub_mkconfig_argv()))
    return steps


async def install(
    config: InstallConfig,
    executor: Executor,
    *,
    on_progress: OnProgress | None = None,
    on_step: Callable[[int], None] | None = None,
) -> None:
    """Install directly through ``executor`` (root/live-CD path)."""
    await run_steps(install_steps(config), executor,
                    on_progress=on_progress, on_step=on_step)


class GrubInstaller(Protocol):
    """The backend calls the installed-system path makes; ``(ok, output)`` each."""

    async def install_grub(
        self, firmware: str, efi_directory: str, bootloader_id: str,
        removable: bool, disk: str, boot_directory: str,
    ) -> tuple[bool, str]: ...

    async def regenerate_grub(self) -> tuple[bool, str]: ...


async def install_via_backend(
    config: InstallConfig,
    backend: GrubInstaller,
    *,
    on_progress: OnProgress | None = None,
    on_step: Callable[[int], None] | None = None,
) -> None:
    """Install through the polkit-gated backend (installed-system path).

    Same two phases as :func:`install`; each is a backend call that re-validates
    server-side. Raises :class:`StepError` at the first phase that fails.
    """

    def _emit(output: str) -> None:
        if on_progress and output:
            on_progress(output.splitlines())

    def _step(index: int) -> None:
        if on_step is not None:
            on_step(index)

    _step(0)
    ok, out = await backend.install_grub(
        config.firmware, config.efi_directory, config.bootloader_id,
        config.removable, config.disk, config.boot_directory)
    _emit(out)
    if not ok:
        raise fail(f"install GRUB ({config.firmware})", out)

    if config.regenerate:
        _step(1)
        ok, out = await backend.regenerate_grub()
        _emit(out)
        if not ok:
            raise fail("regenerate grub.cfg", out)
