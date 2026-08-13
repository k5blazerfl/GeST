"""CI-safe tests for the install-target assembly core: deriving a mount plan,
the mkdir→mount→swapon pipeline, target-root safety, generated fstab, and the
direct + backend apply paths. No disk is touched — the pipeline runs through a
FakeExecutor and a fake backend, and the one real file write goes to a tmp dir
via a monkeypatched allowed-root prefix."""

import asyncio

import pytest

from gest.core.disk import commands, fstab, mount, reader
from gest.core.disk.model import DiskPlan, Filesystem, Partition
from gest.core.exec.executor import FakeExecutor
from gest.core.exec.steps import StepError

# A canned UEFI plan: ESP + swap + root, as uefi_plan would produce.
_PLAN = DiskPlan(
    disk="/dev/sda",
    wipe=True,
    partitions=[
        Partition(1, "512M", "EF00", "ESP"),
        Partition(2, "8G", "8200", "swap"),
        Partition(3, "rest", "8300", "root"),
    ],
    filesystems=[
        Filesystem("/dev/sda1", "vfat", "ESP"),
        Filesystem("/dev/sda2", "swap", "swap"),
        Filesystem("/dev/sda3", "ext4", "root"),
    ],
)


# --- deriving the plan ------------------------------------------------------

def test_derive_maps_roles_orders_root_first_and_separates_swap():
    plan = mount.derive_mount_plan(_PLAN, "/mnt/gentoo")
    assert plan.root == "/mnt/gentoo"
    # root ("/") comes before the nested ESP ("/efi"); swap is not a mount.
    assert [(m.device, m.path, m.fstype) for m in plan.mounts] == [
        ("/dev/sda3", "/", "ext4"),
        ("/dev/sda1", "/efi", "vfat"),
    ]
    assert plan.swap == ["/dev/sda2"]


def test_derive_rejects_unsafe_target_root():
    for bad in ("/", "/home", "/mnt", "relative/path", "/mnt/../etc"):
        with pytest.raises(ValueError):
            mount.derive_mount_plan(_PLAN, bad)


def test_derive_unknown_label_becomes_slashed_path_and_none_label_raises():
    known = DiskPlan(disk="/dev/sda", wipe=False, partitions=[],
                     filesystems=[Filesystem("/dev/sda1", "xfs", "data")])
    assert mount.derive_mount_plan(known, "/mnt/t").mounts[0].path == "/data"
    unlabeled = DiskPlan(disk="/dev/sda", wipe=False, partitions=[],
                         filesystems=[Filesystem("/dev/sda1", "ext4", None)])
    with pytest.raises(ValueError):
        mount.derive_mount_plan(unlabeled, "/mnt/t")


def test_deeper_paths_mount_after_their_parents():
    plan = DiskPlan(disk="/dev/sda", wipe=False, partitions=[], filesystems=[
        Filesystem("/dev/sda4", "xfs", "home"),
        Filesystem("/dev/sda3", "ext4", "root"),
    ])
    ordered = [m.path for m in mount.derive_mount_plan(plan, "/mnt/g").mounts]
    assert ordered == ["/", "/home"]


# --- target-root safety -----------------------------------------------------

def test_valid_target_root():
    assert mount.valid_target_root("/mnt/gentoo")
    assert mount.valid_target_root("/media/usb")
    assert mount.valid_target_root("/run/media/user/x")
    for bad in ("/", "/mnt", "/home", "/etc", "mnt/gentoo", "/mnt/../etc",
                "/mnt/a b", ""):
        assert not mount.valid_target_root(bad)


def test_guard_target_root_raises_on_unsafe():
    mount.guard_target_root("/mnt/gentoo")            # no raise
    with pytest.raises(ValueError):
        mount.guard_target_root("/")


def test_target_abs():
    assert mount.target_abs("/mnt/gentoo", "/") == "/mnt/gentoo"
    assert mount.target_abs("/mnt/gentoo", "/efi") == "/mnt/gentoo/efi"
    assert mount.target_abs("/mnt/gentoo/", "/boot") == "/mnt/gentoo/boot"


# --- command builders -------------------------------------------------------

def test_mkdir_and_mount_device_argv():
    assert commands.mkdir_p_argv("/mnt/gentoo/efi") == ["mkdir", "-p", "/mnt/gentoo/efi"]
    assert commands.mount_device_argv("/dev/sda3", "/mnt/gentoo") == \
        ["mount", "/dev/sda3", "/mnt/gentoo"]


def test_target_path_and_device_validation_rejects_unsafe():
    assert not commands.valid_target_path("/mnt/../etc")
    assert not commands.valid_target_path("relative")
    for bad in ("/mnt/../etc", "relative/x"):
        with pytest.raises(ValueError):
            commands.mkdir_p_argv(bad)
    with pytest.raises(ValueError):
        commands.mount_device_argv("sda3", "/mnt/gentoo")     # not a /dev node
    with pytest.raises(ValueError):
        commands.mount_device_argv("/dev/sda3", "bad/../path")  # traversal in path
    # A syntactically valid path like /etc is accepted here; the /mnt confinement
    # is enforced by mount.valid_target_root and the backend, not this builder.
    assert commands.mount_device_argv("/dev/sda3", "/etc") == ["mount", "/dev/sda3", "/etc"]


# --- the mount pipeline -----------------------------------------------------

def test_mount_steps_order_mkdir_before_mount_root_first_swap_last():
    plan = mount.derive_mount_plan(_PLAN, "/mnt/gentoo")
    steps = mount.mount_steps(plan)
    assert [s.argv for s in steps] == [
        ["mkdir", "-p", "/mnt/gentoo"],
        ["mount", "/dev/sda3", "/mnt/gentoo"],
        ["mkdir", "-p", "/mnt/gentoo/efi"],
        ["mount", "/dev/sda1", "/mnt/gentoo/efi"],
        ["swapon", "/dev/sda2"],
    ]


def test_mount_plan_labels_one_per_phase():
    plan = mount.derive_mount_plan(_PLAN, "/mnt/gentoo")
    assert mount.mount_plan_labels(plan) == [
        "Mount /dev/sda3 → /mnt/gentoo",
        "Mount /dev/sda1 → /mnt/gentoo/efi",
        "Enable swap on /dev/sda2",
    ]


# --- generated fstab --------------------------------------------------------

def test_gen_fstab_entry_options_and_passno_per_kind():
    root = fstab.gen_fstab_entry("R", "/", "ext4")
    assert (root.spec, root.options, root.passno) == ("UUID=R", "noatime", 1)
    esp = fstab.gen_fstab_entry("E", "/efi", "vfat")
    assert (esp.options, esp.passno) == ("umask=0077", 2)
    swp = fstab.gen_fstab_entry("S", "none", "swap")
    assert (swp.options, swp.passno) == ("sw", 0)
    home = fstab.gen_fstab_entry("H", "/home", "xfs")
    assert (home.options, home.passno) == ("defaults", 2)


def test_generate_target_fstab_is_uuid_keyed_and_valid():
    plan = mount.derive_mount_plan(_PLAN, "/mnt/gentoo")
    uuids = {"/dev/sda3": "aaaa", "/dev/sda1": "bbbb", "/dev/sda2": "cccc"}
    text = mount.generate_target_fstab(plan, uuids)
    assert "UUID=aaaa\t/\text4\tnoatime\t0 1" in text
    assert "UUID=bbbb\t/efi\tvfat\tumask=0077\t0 2" in text
    assert "UUID=cccc\tnone\tswap\tsw\t0 0" in text
    assert fstab.valid_generated_fstab(text)


def test_generate_target_fstab_requires_every_uuid():
    plan = mount.derive_mount_plan(_PLAN, "/mnt/gentoo")
    with pytest.raises(ValueError):
        mount.generate_target_fstab(plan, {"/dev/sda3": "aaaa"})   # missing esp/swap


def test_fstab_devices_lists_mounts_and_swap():
    plan = mount.derive_mount_plan(_PLAN, "/mnt/gentoo")
    assert mount.fstab_devices(plan) == ["/dev/sda3", "/dev/sda1", "/dev/sda2"]


def test_valid_generated_fstab_rejects_empty_and_malformed():
    assert not fstab.valid_generated_fstab("# only a comment\n")
    assert not fstab.valid_generated_fstab("UUID=x / ext4\n")       # too few fields


# --- reader (UUID) ----------------------------------------------------------

def test_device_uuid_via_fake_runner():
    calls = []

    def runner(argv):
        calls.append(argv)
        return "\n1234-ABCD\n"

    assert reader.device_uuid("/dev/sda1", runner) == "1234-ABCD"
    assert calls == [["lsblk", "-no", "UUID", "/dev/sda1"]]
    assert reader.parse_lsblk_uuid("") == ""


# --- apply: direct (Executor) path ------------------------------------------

def test_apply_mount_plan_runs_every_step_in_order():
    plan = mount.derive_mount_plan(_PLAN, "/mnt/gentoo")
    ex = FakeExecutor()
    steps = asyncio.run(mount.apply_mount_plan(plan, ex))
    assert [c[0] for c in ex.calls] == \
        ["mkdir", "mount", "mkdir", "mount", "swapon"]
    assert len(ex.calls) == len(steps)


def test_apply_mount_plan_stops_at_first_failure():
    plan = mount.derive_mount_plan(_PLAN, "/mnt/gentoo")
    ex = FakeExecutor(code_for=lambda argv: 1 if argv[0] == "mount" else 0)
    with pytest.raises(StepError):
        asyncio.run(mount.apply_mount_plan(plan, ex))
    # mkdir ran, the first mount failed — nothing after it ran.
    assert [c[0] for c in ex.calls] == ["mkdir", "mount"]


# --- apply: backend (D-Bus) path --------------------------------------------

class _FakeMounter:
    """Records install-target calls; fails the op named in ``fail``."""

    def __init__(self, fail: str | None = None) -> None:
        self.calls: list[str] = []
        self._fail = fail

    async def _do(self, name: str) -> tuple[bool, str]:
        self.calls.append(name)
        return (name != self._fail, f"{name} output")

    async def mount_at(self, device, path):
        return await self._do(f"mount:{device}@{path}")

    async def swapon(self, device):
        return await self._do(f"swapon:{device}")

    async def write_target_fstab(self, target, text):
        return await self._do(f"fstab:{target}")


def test_apply_via_backend_mounts_root_first_then_swap():
    plan = mount.derive_mount_plan(_PLAN, "/mnt/gentoo")
    backend = _FakeMounter()
    asyncio.run(mount.apply_mount_plan_via_backend(plan, backend))
    assert backend.calls == [
        "mount:/dev/sda3@/mnt/gentoo",
        "mount:/dev/sda1@/mnt/gentoo/efi",
        "swapon:/dev/sda2",
    ]


def test_apply_via_backend_raises_and_stops_on_refusal():
    plan = mount.derive_mount_plan(_PLAN, "/mnt/gentoo")
    backend = _FakeMounter(fail="mount:/dev/sda1@/mnt/gentoo/efi")
    with pytest.raises(StepError):
        asyncio.run(mount.apply_mount_plan_via_backend(plan, backend))
    # Root mounted, ESP mount refused — swap never attempted.
    assert backend.calls == [
        "mount:/dev/sda3@/mnt/gentoo",
        "mount:/dev/sda1@/mnt/gentoo/efi",
    ]


# --- direct fstab write (real file, tmp dir via allowed-prefix override) -----

def test_write_target_fstab_file_writes_atomically(tmp_path, monkeypatch):
    monkeypatch.setattr(mount, "ALLOWED_TARGET_ROOTS", (str(tmp_path),))
    root = str(tmp_path / "gentoo")
    text = fstab.render_fstab([fstab.gen_fstab_entry("R", "/", "ext4")])
    path = mount.write_target_fstab_file(root, text)
    assert path == f"{root}/etc/fstab"
    assert "UUID=R\t/\text4\tnoatime\t0 1" in (tmp_path / "gentoo/etc/fstab").read_text()


def test_write_target_fstab_file_refuses_bad_root_and_bad_content(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        mount.write_target_fstab_file("/etc", "anything")          # outside target roots
    monkeypatch.setattr(mount, "ALLOWED_TARGET_ROOTS", (str(tmp_path),))
    with pytest.raises(ValueError):
        mount.write_target_fstab_file(str(tmp_path / "g"), "# comment only\n")
