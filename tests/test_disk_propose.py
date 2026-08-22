"""Phase 1: the guided disk-layout proposal (auto-sizing). Pure — no devices."""

from __future__ import annotations

import pytest

from gest.core.disk import provision

_GIB = 1024 ** 3


def test_swap_equals_ram_up_to_8g():
    assert provision.propose_swap_size(4 * _GIB) == "4G"
    assert provision.propose_swap_size(8 * _GIB) == "8G"


def test_swap_capped_at_16g_for_big_ram():
    assert provision.propose_swap_size(16 * _GIB) == "16G"
    assert provision.propose_swap_size(64 * _GIB) == "16G"


def test_swap_floor_is_1g():
    assert provision.propose_swap_size(0) == "1G"


def test_propose_uefi_layout_has_esp_swap_root():
    plan = provision.propose_layout("vda", 8 * _GIB, "uefi")
    kinds = [f.kind for f in plan.filesystems]
    assert kinds == ["vfat", "swap", "ext4"]        # ESP, swap, root
    esp = plan.partitions[0]
    assert esp.size == provision.ESP_PROPOSAL_SIZE and esp.type_guid == "EF00"
    assert plan.partitions[-1].size == "rest"        # root fills the disk


def test_propose_bios_layout_has_no_esp():
    plan = provision.propose_layout("vda", 8 * _GIB, "bios")
    guids = [p.type_guid for p in plan.partitions]
    assert "EF00" not in guids and "EF02" in guids   # BIOS-boot, not ESP
    assert [f.kind for f in plan.filesystems] == ["swap", "ext4"]


def test_propose_layout_rejects_bad_firmware():
    with pytest.raises(ValueError):
        provision.propose_layout("vda", 8 * _GIB, "coreboot")


def test_propose_layout_respects_root_fs():
    plan = provision.propose_layout("vda", 8 * _GIB, "uefi", root_fs="btrfs")
    assert plan.filesystems[-1].kind == "btrfs"


def test_layout_warning_fires_on_small_disk():
    # 20 GiB disk, 8 GiB RAM → swap 8 + ESP 1 = 9 overhead → ~11 GiB root < 15 → warn
    warn = provision.layout_warning(20 * _GIB, 8 * _GIB, "uefi")
    assert warn is not None and "root" in warn


def test_layout_warning_silent_on_roomy_disk():
    assert provision.layout_warning(500 * _GIB, 16 * _GIB, "uefi") is None


def test_propose_layout_separate_home():
    plan = provision.propose_layout("vda", 8 * _GIB, "uefi",
                                    separate_home=True, root_size="40G", home_fs="ext4")
    assert [f.kind for f in plan.filesystems] == ["vfat", "swap", "ext4", "ext4"]
    assert "home" in [f.label for f in plan.filesystems]
    root = next(p for p in plan.partitions if p.label == "root")
    home = next(p for p in plan.partitions if p.label == "home")
    assert root.size == "40G" and home.size == "rest"   # root fixed, home fills rest


def test_home_needs_a_fixed_root_size():
    import pytest
    with pytest.raises(ValueError):
        provision.uefi_plan("vda", "1G", "8G", "ext4", root_size="rest", home_fs="ext4")


def test_bios_separate_home_has_no_esp():
    plan = provision.propose_layout("vda", 8 * _GIB, "bios",
                                    separate_home=True, root_size="30G")
    assert "EF00" not in [p.type_guid for p in plan.partitions]
    assert [f.label for f in plan.filesystems] == ["swap", "root", "home"]
