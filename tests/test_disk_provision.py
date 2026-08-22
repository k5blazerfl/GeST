"""CI-safe tests for the disk provisioning core: argv builders, safety
validation, and the ordered apply pipeline. No disk is touched — the pipeline is
driven through a FakeExecutor."""

import asyncio

import pytest

from gest.core.disk import commands, provision
from gest.core.disk.model import BlockDevice, DiskPlan, Filesystem, Partition
from gest.core.exec.executor import FakeExecutor

# A disk with no mounted children — the safe, unpartitioned scratch target.
_DEVICES = [
    BlockDevice(name="sda", type="disk", children=[]),
    BlockDevice(
        name="nvme0n1",
        type="disk",
        children=[BlockDevice(name="nvme0n1p1", type="part", mountpoint="/")],
    ),
]
_MOUNTS = "/dev/nvme0n1p1 / ext4 rw,relatime 0 0\nproc /proc proc rw 0 0\n"

_PLAN = DiskPlan(
    disk="/dev/sda",
    wipe=True,
    partitions=[
        Partition(1, "512M", "EF00", "esp"),
        Partition(2, "rest", "8300", "root"),
    ],
    filesystems=[
        Filesystem("/dev/sda1", "vfat", "ESP"),
        Filesystem("/dev/sda2", "ext4", "root"),
    ],
)


# --- argv builders ----------------------------------------------------------

def test_sgdisk_partition_argv_encodes_each_partition():
    argv = commands.sgdisk_partition_argv("/dev/sda", _PLAN.partitions)
    assert argv[0] == "sgdisk" and argv[-1] == "/dev/sda"
    assert "-n" in argv and "1:0:+512M" in argv        # sized partition
    assert "2:0:0" in argv                             # "rest" -> end sentinel 0
    assert "1:EF00" in argv and "2:8300" in argv       # type codes
    assert "1:esp" in argv and "2:root" in argv        # labels


def test_mkfs_argv_per_kind():
    assert commands.mkfs_argv("/dev/sda2", "ext4", "root") == \
        ["mkfs.ext4", "-F", "-L", "root", "/dev/sda2"]
    assert commands.mkfs_argv("/dev/sda2", "ext3", "root") == \
        ["mkfs.ext3", "-F", "-L", "root", "/dev/sda2"]
    assert commands.mkfs_argv("/dev/sda1", "vfat", "ESP") == \
        ["mkfs.vfat", "-F", "32", "-n", "ESP", "/dev/sda1"]
    assert commands.mkfs_argv("/dev/sda3", "btrfs") == ["mkfs.btrfs", "-f", "/dev/sda3"]
    # interop/data filesystems: ntfs quick+force, exfat quick-by-default.
    assert commands.mkfs_argv("/dev/sda4", "ntfs", "data") == \
        ["mkfs.ntfs", "-Q", "-F", "-L", "data", "/dev/sda4"]
    assert commands.mkfs_argv("/dev/sda5", "exfat", "share") == \
        ["mkfs.exfat", "-L", "share", "/dev/sda5"]


def test_swap_builders():
    assert commands.mkswap_argv("/dev/sda3", "swp") == ["mkswap", "-L", "swp", "/dev/sda3"]
    assert commands.swapon_argv("/dev/sda3") == ["swapon", "/dev/sda3"]


@pytest.mark.parametrize("dev,ok", [
    ("/dev/sda", True), ("/dev/nvme0n1p2", True), ("/dev/mapper/vg-root", True),
    ("/etc/passwd", False), ("/dev/../etc/shadow", False), ("sda", False), ("/dev/a b", False),
])
def test_valid_device(dev, ok):
    assert commands.valid_device(dev) is ok


def test_builders_reject_bad_inputs():
    with pytest.raises(ValueError):
        commands.mkfs_argv("/dev/sda1", "reiser4")             # unknown fs
    with pytest.raises(ValueError):
        commands.sgdisk_partition_argv("/dev/sda", [Partition(1, "8Q", "EF00")])  # bad size
    with pytest.raises(ValueError):
        commands.sgdisk_partition_argv("/dev/sda", [Partition(1, "1G", "ZZZZ")])  # bad guid
    with pytest.raises(ValueError):
        commands.wipefs_argv("/dev/sda; rm -rf /")             # bad device


# --- safety validation ------------------------------------------------------

def test_validate_accepts_clean_scratch_disk():
    assert provision.validate_plan(_PLAN, _DEVICES, _MOUNTS) == []


def test_validate_refuses_unknown_device():
    plan = DiskPlan(disk="/dev/sdz", wipe=True, partitions=[Partition(1, "rest", "8300")])
    problems = provision.validate_plan(plan, _DEVICES, _MOUNTS)
    assert any("not a present block device" in p for p in problems)


def test_validate_refuses_mounted_disk():
    plan = DiskPlan(disk="/dev/nvme0n1", wipe=True, partitions=[Partition(1, "rest", "8300")])
    problems = provision.validate_plan(plan, _DEVICES, _MOUNTS)
    assert any("mounted partition" in p for p in problems)


def test_validate_refuses_live_medium():
    problems = provision.validate_plan(_PLAN, _DEVICES, _MOUNTS, boot_source="/dev/sda")
    assert any("live/boot medium" in p for p in problems)


def test_mounted_sources_parses_proc_mounts():
    assert provision.mounted_sources(_MOUNTS) == {"/dev/nvme0n1p1"}


# --- pipeline ordering ------------------------------------------------------

def test_plan_steps_order_is_wipe_partition_settle_then_mkfs():
    labels = [s.label for s in provision.plan_steps(_PLAN)]
    i_wipe = next(i for i, s in enumerate(labels) if s.startswith("wipe"))
    i_part = next(i for i, s in enumerate(labels) if s.startswith("create partitions"))
    i_settle = next(i for i, s in enumerate(labels) if s == "settle udev")
    i_mkfs = next(i for i, s in enumerate(labels) if s.startswith("make ext4"))
    assert i_wipe < i_part < i_settle < i_mkfs


def test_plan_steps_no_wipe_skips_wipe_steps():
    plan = DiskPlan(disk="/dev/sda", wipe=False, partitions=[Partition(1, "rest", "8300")],
                    filesystems=[Filesystem("/dev/sda1", "ext4")])
    labels = [s.label for s in provision.plan_steps(plan)]
    assert not any(s.startswith("wipe") or s.startswith("zap") for s in labels)


# --- apply ------------------------------------------------------------------

def test_apply_runs_every_step_in_order():
    ex = FakeExecutor()
    steps = asyncio.run(provision.apply_plan(_PLAN, ex, _DEVICES, _MOUNTS))
    assert [c[0] for c in ex.calls] == \
        ["wipefs", "sgdisk", "sgdisk", "partprobe", "udevadm", "mkfs.vfat", "mkfs.ext4"]
    assert len(ex.calls) == len(steps)


def test_apply_refuses_unsafe_plan_without_running_anything():
    ex = FakeExecutor()
    with pytest.raises(provision.DiskSafetyError):
        asyncio.run(provision.apply_plan(_PLAN, ex, _DEVICES, _MOUNTS, boot_source="/dev/sda"))
    assert ex.calls == []


def test_apply_stops_at_first_failing_step():
    ex = FakeExecutor(code_for=lambda argv: 1 if argv[0] == "sgdisk" else 0)
    with pytest.raises(provision.DiskApplyError) as excinfo:
        asyncio.run(provision.apply_plan(_PLAN, ex, _DEVICES, _MOUNTS))
    # wipefs ran, then the first sgdisk failed — nothing after it ran.
    assert [c[0] for c in ex.calls] == ["wipefs", "sgdisk"]
    assert excinfo.value.result.code == 1


# --- server-side guards (what the backend re-checks) ------------------------

def test_root_source_finds_root_device():
    assert provision.root_source(_MOUNTS) == "/dev/nvme0n1p1"
    assert provision.root_source("proc /proc proc rw 0 0\n") is None


def test_guard_whole_disk_refuses_mounted_and_root():
    # The disk holding the running root is refused for partitioning.
    with pytest.raises(provision.DiskSafetyError):
        provision.guard_provision_target("/dev/nvme0n1", _MOUNTS, whole_disk=True)
    # A clean scratch disk passes.
    provision.guard_provision_target("/dev/sda", _MOUNTS, whole_disk=True)


def test_guard_partition_refuses_mounted_target():
    with pytest.raises(provision.DiskSafetyError):
        provision.guard_provision_target("/dev/nvme0n1p1", _MOUNTS, whole_disk=False)
    provision.guard_provision_target("/dev/sda2", _MOUNTS, whole_disk=False)


# --- backend-path orchestration ---------------------------------------------

class _FakeBackend:
    """Records provisioning calls; fails the op named in ``fail``."""

    def __init__(self, fail: str | None = None) -> None:
        self.calls: list[str] = []
        self._fail = fail

    async def _do(self, name: str) -> tuple[bool, str]:
        self.calls.append(name)
        return (name != self._fail, f"{name} output")

    async def partition_disk(self, disk, wipe, partitions):
        return await self._do("partition")

    async def make_filesystem(self, device, kind, label):
        return await self._do(f"mkfs:{device}")

    async def make_swap(self, device, label):
        return await self._do(f"mkswap:{device}")

    async def swapon(self, device):
        return await self._do(f"swapon:{device}")


def test_apply_via_backend_calls_partition_then_filesystems():
    backend = _FakeBackend()
    asyncio.run(provision.apply_via_backend(_PLAN, backend))
    assert backend.calls == ["partition", "mkfs:/dev/sda1", "mkfs:/dev/sda2"]


def test_apply_via_backend_formats_swap_but_does_not_swapon():
    # provision only mkswaps (formats); the mount step swapons it. Doing both
    # double-activates → the second swapon fails "Device or resource busy".
    plan = DiskPlan(disk="/dev/sda", wipe=False, partitions=[Partition(1, "rest", "8200")],
                    filesystems=[Filesystem("/dev/sda1", "swap", "swp")])
    backend = _FakeBackend()
    asyncio.run(provision.apply_via_backend(plan, backend))
    assert backend.calls == ["partition", "mkswap:/dev/sda1"]     # no swapon here


def test_apply_via_backend_raises_on_refusal():
    backend = _FakeBackend(fail="partition")
    with pytest.raises(provision.DiskApplyError):
        asyncio.run(provision.apply_via_backend(_PLAN, backend))
    assert backend.calls == ["partition"]        # stopped before any mkfs


def test_on_step_reports_each_phase_index():
    seen: list[int] = []
    asyncio.run(provision.apply_plan(_PLAN, FakeExecutor(), _DEVICES, _MOUNTS,
                                     on_step=seen.append))
    assert seen == list(range(len(provision.plan_steps(_PLAN))))


def test_on_step_via_backend_is_one_per_phase():
    seen: list[int] = []
    asyncio.run(provision.apply_via_backend(_PLAN, _FakeBackend(), on_step=seen.append))
    # one partition phase + one per filesystem
    assert seen == [0, 1, 2] == list(range(len(provision.plan_phase_labels(_PLAN))))


# --- UEFI layout builder ----------------------------------------------------

def test_partition_device_naming():
    assert provision.partition_device("sda", 2) == "/dev/sda2"
    assert provision.partition_device("nvme0n1", 2) == "/dev/nvme0n1p2"


def test_uefi_plan_with_swap():
    plan = provision.uefi_plan("sda", "512M", "8G", "ext4")
    assert plan.disk == "/dev/sda" and plan.wipe
    assert [(p.number, p.size, p.type_guid) for p in plan.partitions] == \
        [(1, "512M", "EF00"), (2, "8G", "8200"), (3, "rest", "8300")]
    assert [(f.device, f.kind) for f in plan.filesystems] == \
        [("/dev/sda1", "vfat"), ("/dev/sda2", "swap"), ("/dev/sda3", "ext4")]
    labels = provision.plan_phase_labels(plan)
    assert labels[0] == "Partition /dev/sda" and "Enable swap" in labels[2]


def test_uefi_plan_without_swap():
    plan = provision.uefi_plan("nvme0n1", "512M", "", "btrfs")
    assert [f.device for f in plan.filesystems] == ["/dev/nvme0n1p1", "/dev/nvme0n1p2"]
    assert plan.filesystems[-1].kind == "btrfs"


def test_uefi_plan_rejects_bad_root_fs():
    with pytest.raises(ValueError):
        provision.uefi_plan("sda", "512M", "", "swap")     # swap isn't a root fs
    with pytest.raises(ValueError):
        provision.uefi_plan("sda", "512M", "", "reiser4")  # unsupported
    # mkfs-supported but NOT bootable as a Linux root — must be rejected here even
    # though commands.mkfs_argv can make them (they are data/interop only).
    for bad in ("vfat", "ntfs", "exfat"):
        with pytest.raises(ValueError):
            provision.uefi_plan("sda", "512M", "", bad)
    # ext3 IS a valid root and must be accepted.
    provision.uefi_plan("sda", "512M", "", "ext3")


def test_bios_plan_with_swap():
    plan = provision.bios_plan("sda", "8G", "ext4")
    assert plan.disk == "/dev/sda" and plan.wipe
    # A BIOS-boot partition (EF02) leads, then swap, then root; no ESP.
    assert [(p.number, p.size, p.type_guid) for p in plan.partitions] == \
        [(1, "2M", "EF02"), (2, "8G", "8200"), (3, "rest", "8300")]
    # The EF02 partition carries no filesystem — it never gets mkfs'd, mounted, or
    # written to fstab (GRUB embeds core.img into it raw).
    assert [(f.device, f.kind) for f in plan.filesystems] == \
        [("/dev/sda2", "swap"), ("/dev/sda3", "ext4")]
    assert "EF00" not in [p.type_guid for p in plan.partitions]   # no ESP


def test_bios_plan_without_swap():
    plan = provision.bios_plan("nvme0n1", "", "xfs")
    assert [(p.number, p.type_guid) for p in plan.partitions] == [(1, "EF02"), (2, "8300")]
    assert [(f.device, f.kind) for f in plan.filesystems] == [("/dev/nvme0n1p2", "xfs")]


def test_bios_plan_rejects_bad_root_fs():
    with pytest.raises(ValueError):
        provision.bios_plan("sda", "", "swap")
    with pytest.raises(ValueError):
        provision.bios_plan("sda", "", "reiser4")
