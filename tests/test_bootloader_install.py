"""CI-safe tests for bootloader install: grub argv builders, the install
pipeline, and both apply paths (direct via FakeExecutor, backend via a fake)."""

import asyncio

import pytest

from gest.core.bootloader import commands, install, m1n1, seamless
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


# --- arch → GRUB target -----------------------------------------------------

def test_grub_target_mapping():
    assert commands.grub_target("amd64", "uefi") == "x86_64-efi"
    assert commands.grub_target("amd64", "bios") == "i386-pc"
    assert commands.grub_target("arm64", "uefi") == "arm64-efi"  # Apple Silicon/Asahi


@pytest.mark.parametrize("arch,firmware", [
    ("arm64", "bios"),   # no BIOS GRUB on arm64
    ("riscv", "uefi"),   # unknown arch
])
def test_grub_target_rejects_unsupported(arch, firmware):
    with pytest.raises(ValueError):
        commands.grub_target(arch, firmware)


def test_grub_install_uefi_arm64_target():
    assert commands.grub_install_argv("uefi", arch="arm64") == [
        "grub-install", "--target=arm64-efi", "--efi-directory=/efi",
        "--bootloader-id=GRUB"]


def test_install_steps_threads_arch_to_target():
    cfg = install.InstallConfig(firmware="uefi", regenerate=False)
    steps = install.install_steps(cfg, arch="arm64")
    assert "--target=arm64-efi" in steps[0].argv


# --- m1n1 boot stub (Apple Silicon / Asahi) ---------------------------------

def test_m1n1_default_boot_bin():
    assert m1n1.default_boot_bin("/efi") == "/efi/m1n1/boot.bin"
    assert m1n1.default_boot_bin("/boot/efi/") == "/boot/efi/m1n1/boot.bin"


def test_update_m1n1_argv():
    assert m1n1.update_m1n1_argv() == ["update-m1n1"]           # tool uses its config
    assert m1n1.update_m1n1_argv("/efi/m1n1/boot.bin") == [
        "update-m1n1", "/efi/m1n1/boot.bin"]


@pytest.mark.parametrize("bad", ["rel/path", "/etc/../x", "/a\nb"])
def test_update_m1n1_rejects_bad_path(bad):
    with pytest.raises(ValueError):
        m1n1.update_m1n1_argv(bad)


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

    async def configure_seamless_boot(self, root):
        self.calls.append("seamless")
        return (self._fail != "seamless", "seamless output")

    async def regenerate_grub(self):
        self.calls.append("regenerate")
        return (self._fail != "regenerate", "regen output")


def test_install_steps_seamless_writes_default_and_stages_before_regenerate():
    cfg = install.InstallConfig(firmware="uefi", seamless=True,
                                root="/nonexistent-seamless-test")
    steps = install.install_steps(cfg)
    labels = [s.label for s in steps]
    assert labels[0].startswith("install GRUB")
    assert labels[-1] == "regenerate grub.cfg"
    write = next(s for s in steps if s.argv and s.argv[0] == "tee")
    assert write.argv[1] == "/nonexistent-seamless-test/etc/default/grub"
    assert seamless.SEAMLESS_CMDLINE in (write.stdin or "")   # merged content on stdin
    assert any(s.argv[0] == "cp" for s in steps)              # theme staged
    assert any(s.argv[0] == "plymouth-set-default-theme" for s in steps)


def test_install_steps_no_seamless_by_default():
    steps = install.install_steps(install.InstallConfig(firmware="uefi"))
    assert not any(s.argv and s.argv[0] == "tee" for s in steps)


def test_install_via_backend_calls_install_then_regenerate():
    backend = _FakeBackend()
    asyncio.run(install.install_via_backend(install.InstallConfig(firmware="uefi"), backend))
    assert backend.calls == ["install", "regenerate"]  # no seamless by default


def test_install_via_backend_seamless_between_install_and_regenerate():
    backend = _FakeBackend()
    cfg = install.InstallConfig(firmware="uefi", seamless=True)
    asyncio.run(install.install_via_backend(cfg, backend))
    assert backend.calls == ["install", "seamless", "regenerate"]


def test_install_via_backend_stops_on_failed_seamless():
    backend = _FakeBackend(fail="seamless")
    cfg = install.InstallConfig(firmware="uefi", seamless=True)
    with pytest.raises(StepError):
        asyncio.run(install.install_via_backend(cfg, backend))
    assert backend.calls == ["install", "seamless"]  # stops before regenerate


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
