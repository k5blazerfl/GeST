"""CI-safe tests for the bootloader core (pure parsing + argv builder)."""

import pytest

from gest.core.bootloader import commands, reader


def test_parse_boot_kernels_newest_first():
    names = [
        "vmlinuz-6.18.35-gentoo-dist", "config-6.18.35-gentoo-dist",
        "vmlinuz-7.1.5-gentoo-dist", "initramfs-7.1.5-gentoo-dist.img",
        "kernel-5.10.0", "System.map-7.1.5-gentoo-dist", "grub",
    ]
    assert reader.parse_boot_kernels(names) == [
        "7.1.5-gentoo-dist", "6.18.35-gentoo-dist", "5.10.0",
    ]


def test_parse_boot_kernels_empty():
    assert reader.parse_boot_kernels(["grub", "amd-uc.img"]) == []


def test_grub_mkconfig_argv():
    assert commands.grub_mkconfig_argv() == ["grub-mkconfig", "-o", "/boot/grub/grub.cfg"]
    argv = commands.grub_mkconfig_argv(
        "/boot/grub/grub.cfg", grub_mkconfig="/usr/sbin/grub-mkconfig"
    )
    assert argv[0] == "/usr/sbin/grub-mkconfig"


@pytest.mark.parametrize("bad", ["boot/grub.cfg", "/etc/x\ny", "relative"])
def test_grub_mkconfig_argv_rejects(bad):
    with pytest.raises(ValueError):
        commands.grub_mkconfig_argv(bad)
