"""The Disk gate's Handbook-style context: size parsing + the on-screen partition
breakdown. The breakdown is derived from the real DiskPlan, so these tests guard
that what the user reads on the Disk gate matches what actually gets written."""

from __future__ import annotations

import types

from gest.tui.screens.install import wizard

_GIB = 1024 ** 3


def test_size_to_bytes_parses_lsblk_human_sizes():
    assert wizard._size_to_bytes("16G") == 16 * _GIB
    assert wizard._size_to_bytes("512M") == 512 * 1024 ** 2
    assert wizard._size_to_bytes("1.8T") == int(1.8 * 1024 ** 4)
    assert wizard._size_to_bytes("238.5G") == int(238.5 * _GIB)
    assert wizard._size_to_bytes("1024") == 1024        # bare bytes


def test_size_to_bytes_is_forgiving():
    assert wizard._size_to_bytes("") == 0
    assert wizard._size_to_bytes("junk") == 0
    assert wizard._size_to_bytes(None) == 0             # type: ignore[arg-type]


def _step(**over):
    """A DiskStep with selections, without constructing the urwid App."""
    sel = types.SimpleNamespace(
        disk="sda", firmware="uefi", esp_size="1G", swap_size="8G",
        root_fs="ext4", separate_home=False, root_size="40G", home_fs="ext4")
    for k, v in over.items():
        setattr(sel, k, v)
    step = wizard.DiskStep.__new__(wizard.DiskStep)
    step.sel = sel
    return step


def _lines(step):
    return [label for (label, value, _a) in step._partition_rows()]


def test_uefi_breakdown_lists_esp_swap_root_in_order():
    lines = _lines(_step())
    assert "1. /boot/efi" in lines[0] and "vfat" in lines[0]
    assert "2. swap" in lines[1] and "swap" in lines[1]
    assert "3. /" in lines[2] and "rest" in lines[2] and "ext4" in lines[2]


def test_bios_breakdown_has_raw_bios_boot_and_no_esp():
    lines = _lines(_step(firmware="bios"))
    assert "(raw)" in lines[0], lines           # BIOS-boot partition, no filesystem
    assert not any("/boot/efi" in ln for ln in lines)


def test_separate_home_breakdown_adds_home_partition():
    lines = _lines(_step(separate_home=True))
    assert any("/home" in ln for ln in lines)
    assert any("40G" in ln for ln in lines)     # fixed root size, not "rest"


def test_invalid_selections_fall_back_gracefully():
    # A bad ESP size makes uefi_plan raise; the gate must not crash.
    lines = _lines(_step(esp_size="notasize"))
    assert len(lines) == 1 and "adjust" in lines[0]


def test_space_warning_fires_on_a_too_small_disk():
    disks = [types.SimpleNamespace(name="sda", size="20G")]
    assert _step()._space_warning(disks)                       # ~3 GiB root left
    disks = [types.SimpleNamespace(name="sda", size="500G")]
    assert _step()._space_warning(disks) is None


def test_target_label_shows_disk_size():
    disks = [types.SimpleNamespace(name="sda", size="238.5G")]
    assert _step()._target_label(disks) == "sda (238.5G)"
    assert _step(disk="")._target_label(disks) == "(none — required)"
