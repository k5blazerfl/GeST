"""CI-safe tests for bootloader install: grub argv builders, the install
pipeline, and both apply paths (direct via FakeExecutor, backend via a fake)."""

import asyncio

import pytest

from gest.core.bootloader import commands, install
from gest.core.exec.executor import FakeExecutor
from gest.core.exec.steps import StepError, run_steps

# --- grub-install argv ------------------------------------------------------

def test_grub_install_uefi_default():
    assert commands.grub_install_argv("uefi") == [
        "grub-install", "--target=x86_64-efi", "--efi-directory=/efi",
        "--bootloader-id=GRUB"]


def test_grub_install_uefi_removable_and_boot_dir():
    argv = commands.grub_install_argv(
        "uefi", efi_directory="/mnt/gentoo/efi", bootloader_id="gentoo",
        removable=True, boot_directory="/mnt/gentoo/boot")
    assert "--removable" in argv
    assert "--efi-directory=/mnt/gentoo/efi" in argv
    assert "--bootloader-id=gentoo" in argv
    assert "--boot-directory=/mnt/gentoo/boot" in argv


def test_grub_install_bios_puts_disk_last():
    assert commands.grub_install_argv("bios", disk="/dev/sda") == [
        "grub-install", "--target=i386-pc", "/dev/sda"]


@pytest.mark.parametrize("call", [
    lambda: commands.grub_install_argv("coreboot"),               # unknown firmware
    lambda: commands.grub_install_argv("bios", disk="sda"),        # not a device
    lambda: commands.grub_install_argv("bios", disk="/dev/../x"),  # traversal
    lambda: commands.grub_install_argv("uefi", bootloader_id="bad id"),  # bad id
    lambda: commands.grub_install_argv("uefi", efi_directory="rel"),     # not absolute
])
def test_grub_install_rejects_bad_input(call):
    with pytest.raises(ValueError):
        call()


# --- pipeline ---------------------------------------------------------------

def test_install_steps_install_then_regenerate():
    cfg = install.InstallConfig(firmware="uefi")
    labels = [s.label for s in install.install_steps(cfg)]
    assert labels == ["install GRUB (uefi)", "regenerate grub.cfg"]


def test_install_steps_skips_regenerate_when_disabled():
    cfg = install.InstallConfig(firmware="bios", disk="/dev/sda", regenerate=False)
    steps = install.install_steps(cfg)
    assert len(steps) == 1 and steps[0].argv[-1] == "/dev/sda"


# --- direct path ------------------------------------------------------------

def test_install_direct_runs_grub_install_then_mkconfig():
    ex = FakeExecutor()
    cfg = install.InstallConfig(firmware="uefi")
    seen: list[int] = []
    asyncio.run(install.install(cfg, ex, on_step=seen.append))
    assert [c[0] for c in ex.calls] == ["grub-install", "grub-mkconfig"]
    assert seen == [0, 1]


def test_install_direct_raises_step_error_on_failure():
    ex = FakeExecutor(code_for=lambda argv: 1 if argv[0] == "grub-install" else 0)
    with pytest.raises(StepError):
        asyncio.run(install.install(install.InstallConfig(firmware="uefi"), ex))
    assert [c[0] for c in ex.calls] == ["grub-install"]      # stopped after failure


# --- backend path -----------------------------------------------------------

class _FakeBackend:
    def __init__(self, fail: str | None = None) -> None:
        self.calls: list[str] = []
        self._fail = fail

    async def install_grub(self, firmware, efi_directory, bootloader_id,
                           removable, disk, boot_directory):
        self.calls.append("install")
        return (self._fail != "install", "install output")

    async def regenerate_grub(self):
        self.calls.append("regenerate")
        return (self._fail != "regenerate", "regen output")


def test_install_via_backend_calls_install_then_regenerate():
    backend = _FakeBackend()
    asyncio.run(install.install_via_backend(install.InstallConfig(firmware="uefi"), backend))
    assert backend.calls == ["install", "regenerate"]


def test_install_via_backend_stops_on_failed_install():
    backend = _FakeBackend(fail="install")
    with pytest.raises(StepError):
        asyncio.run(install.install_via_backend(install.InstallConfig(firmware="uefi"), backend))
    assert backend.calls == ["install"]


# --- shared run_steps -------------------------------------------------------

def test_run_steps_reports_index_and_stops_on_failure():
    from gest.core.exec.steps import Step
    ex = FakeExecutor(code_for=lambda argv: 1 if argv == ["b"] else 0)
    seen: list[int] = []
    with pytest.raises(StepError):
        asyncio.run(run_steps([Step("a", ["a"]), Step("b", ["b"]), Step("c", ["c"])],
                              ex, on_step=seen.append))
    assert seen == [0, 1] and [c for c in ex.calls] == [["a"], ["b"]]
