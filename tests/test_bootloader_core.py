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
    # Defensive: write via shell stdout-redirect (not grub-mkconfig's -o, which has
    # produced an empty grub.cfg inside the installer), retry once, commit only a
    # non-empty result (test -s) so an empty config fails loudly (bug #13).
    argv = commands.grub_mkconfig_argv()
    assert argv[0] == "sh" and argv[1] == "-c"
    script = argv[2]
    assert "grub-mkconfig >/boot/grub/grub.cfg.gest-new" in script
    assert "test -s /boot/grub/grub.cfg.gest-new" in script       # retry + non-empty gate
    assert "mv -f /boot/grub/grub.cfg.gest-new /boot/grub/grub.cfg" in script
    assert "-o" not in script                                     # NOT grub-mkconfig -o
    # honours a custom grub-mkconfig path
    argv2 = commands.grub_mkconfig_argv(
        "/boot/grub/grub.cfg", grub_mkconfig="/usr/sbin/grub-mkconfig")
    assert "/usr/sbin/grub-mkconfig >/boot/grub/grub.cfg.gest-new" in argv2[2]


@pytest.mark.parametrize("bad", ["boot/grub.cfg", "/etc/x\ny", "relative"])
def test_grub_mkconfig_argv_rejects(bad):
    with pytest.raises(ValueError):
        commands.grub_mkconfig_argv(bad)
