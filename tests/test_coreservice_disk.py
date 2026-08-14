"""CI-safe tests for the gestd Disk adapter (pure converter + contract shape)."""

from gest.core.disk.model import BlockDevice
from gest.coreservice import disk_adapter as adapter
from gest.ipc import core_contract


def test_device_to_dict_shape():
    b = BlockDevice(name="sda", size="500G", type="disk", fstype="", mountpoint="")
    d = adapter.device_to_dict(b)
    assert d == {"name": "sda", "size": "500G", "type": "disk",
                 "fstype": "", "mountpoint": ""}
    p = adapter.device_to_dict(
        BlockDevice(name="sda1", size="512M", type="part", fstype="vfat", mountpoint="/boot"))
    assert p["fstype"] == "vfat" and p["mountpoint"] == "/boot" and p["type"] == "part"


def test_disk_contract_shape():
    assert core_contract.DISK_CORE_IFACE == "org.gentoo.gest.core1.Disk"
    assert core_contract.DISK_CORE_PATH == "/org/gentoo/gest/core/Disk"
