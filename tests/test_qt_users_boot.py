"""Tests for the Users + Boot/Kernel pure helpers."""

from gest.core.bootloader.reader import BootInfo
from gest.core.kernel.reader import KernelBuildInfo
from gest.core.users.model import User
from gest.qt.boot import boot_summary
from gest.qt.users import user_label


def test_user_label():
    u = User(name="alice", uid=1000, gid=1000, gecos="Alice Smith,,,")
    assert user_label(u) == "alice — Alice Smith"
    root = User(name="root", uid=0, gid=0)
    assert user_label(root) == "root (system)"


def test_boot_summary():
    boot = BootInfo(
        running_kernel="6.9.1-gentoo",
        kernel_source="linux-6.9.1",
        bootloader="grub",
        kernels=["vmlinuz-6.9.1"],
    )
    kern = KernelBuildInfo(has_config=True, genkernel=True)
    rows = dict(boot_summary(boot, kern))
    assert rows["Running kernel"] == "6.9.1-gentoo"
    assert rows["Bootloader"] == "grub"
    assert rows["Kernel .config"] == "present"
    assert rows["Build tools"] == "genkernel"
