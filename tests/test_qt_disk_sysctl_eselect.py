"""Tests for the Disk / sysctl / eselect pure helpers."""

from gest.core.disk.model import BlockDevice
from gest.core.eselect.model import Target
from gest.qt.disk import device_label
from gest.qt.eselect import target_label
from gest.qt.sysctl import merged_settings


def test_device_label():
    dev = BlockDevice(name="sda1", size="512M", type="part", fstype="vfat", mountpoint="/boot")
    assert device_label(dev) == "sda1  512M  vfat  → /boot"
    bare = BlockDevice(name="sdb", size="8G", type="disk")
    assert device_label(bare) == "sdb  8G"


def test_merged_settings():
    assert merged_settings({"a": "1"}, "b", "2") == {"a": "1", "b": "2"}
    assert merged_settings({"a": "1"}, "a", "9") == {"a": "9"}  # overwrite


def test_target_label():
    assert target_label(Target(number=1, name="python3.13", current=True)) == "python3.13 (current)"
    assert target_label(Target(number=2, name="python3.12")) == "python3.12"
