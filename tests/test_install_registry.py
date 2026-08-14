"""CI-safe tests for the install step registry (step 4b): the twenty Handbook
steps wired to the real module functions. Hermetic — a FakeExecutor and tmp_path
files, no real disk/mount/network. Two things are checked: the ordered registry
(labels/phases/markers/chroot flags) as a pure value, and — over a FakeExecutor —
that every chroot step's argv is ``chroot <root> …`` and the pseudo-fs mounts
bracket them (prepare before, teardown after)."""

import asyncio
import os

import pytest

from gest.core.bootloader.install import InstallConfig
from gest.core.disk import mount as disk_mount
from gest.core.disk import provision
from gest.core.exec.chroot import ChrootExecutor
from gest.core.exec.executor import FakeExecutor
from gest.core.install.context import InstallContext, StateStore
from gest.core.install.engine import run_install
from gest.core.install.plan import InstallPlan, Phase, UserSpec
from gest.core.install.registry import (
    CreateUser,
    EmergeWorld,
    SetHostname,
    SetRootPassword,
    build_registry,
)
from gest.core.install.write import write_under_root
from gest.core.kernel.build import BuildConfig
from gest.core.stage3 import commands as stage3_commands
from gest.core.stage3.model import Stage3Selection

_ROOT = "/mnt/gentoo"

_EXPECTED_LABELS = [
    "Partition the disk",
    "Make filesystems",
    "Mount the target",
    "Unpack the stage3 tarball",
    "Generate /etc/fstab",
    "Write make.conf",
    "Prepare the chroot",
    "Sync the Portage tree",
    "Select the profile",
    "Emerge @world",
    "Set timezone and locale",
    "Set the hostname",
    "Set the console keymap",
    "Build the kernel",
    "Install the bootloader",
    "Set the root password",
    "Create the user account",
    "Configure the network",
]

# The six marker-gated steps (§6) and the one step that opens the chroot.
_MARKER_KEYS = {
    "Partition the disk": "partition",
    "Unpack the stage3 tarball": "unpack_stage3",
    "Sync the Portage tree": "sync_tree",
    "Emerge @world": "emerge_world",
    "Build the kernel": "build_kernel",
    "Install the bootloader": "install_bootloader",
}
_CHROOT_LABELS = {
    "Sync the Portage tree", "Select the profile", "Emerge @world",
    "Build the kernel", "Install the bootloader", "Set the root password",
    "Create the user account",
}
_PHASE_ORDER = list(Phase)


def _plan(*, user=None):
    disk = provision.uefi_plan("sda", "512M", "8G", "ext4")
    return InstallPlan(
        disk=disk,
        mount=disk_mount.derive_mount_plan(disk, _ROOT),
        stage3=Stage3Selection(
            url="https://mirror/stage3.tar.xz",
            filename="stage3.tar.xz",
            size=1,
            digests_url="https://mirror/stage3.tar.xz.DIGESTS",
            signature_url="https://mirror/stage3.tar.xz.asc"),
        kernel=BuildConfig(method="make", jobs=2),
        bootloader=InstallConfig(firmware="uefi"),
        hostname="gentoo",
        timezone="UTC",
        locale="en_US.UTF-8",
        keymap="us",
        user=user,
    )


def _ctx(executor, root=_ROOT, *, plan=None, target_root=_ROOT):
    return InstallContext(
        root=root, host=executor, target=ChrootExecutor(executor, target_root),
        state=StateStore(), plan=plan or _plan())


# --- pure registry ordering / markers ---------------------------------------

def test_registry_is_handbook_ordered():
    reg = build_registry(_plan())
    assert [s.label for s in reg] == _EXPECTED_LABELS


def test_registry_phases_are_non_decreasing():
    reg = build_registry(_plan())
    indices = [_PHASE_ORDER.index(s.phase) for s in reg]
    assert indices == sorted(indices)
    # the exact phase grouping
    assert [s.phase for s in reg[:3]] == [Phase.PREPARE_DISK] * 3
    assert [s.phase for s in reg[3:10]] == [Phase.BASE_SYSTEM] * 7
    assert [s.phase for s in reg[10:13]] == [Phase.CONFIGURE] * 3
    assert [s.phase for s in reg[13:15]] == [Phase.KERNEL_BOOT] * 2
    assert [s.phase for s in reg[15:18]] == [Phase.USERS_NETWORK] * 3


def test_registry_chroot_and_opens_chroot_flags():
    reg = build_registry(_plan())
    assert {s.label for s in reg if s.chroot} == _CHROOT_LABELS
    opens = [s for s in reg if s.opens_chroot]
    assert [s.label for s in opens] == ["Prepare the chroot"]


def test_registry_marker_keys():
    reg = build_registry(_plan())
    keyed = {s.label: s.key for s in reg if hasattr(s, "key")}
    assert keyed == _MARKER_KEYS


def test_tier2_default_empty():
    assert len(build_registry(_plan())) == 18            # rows 1-18; 2 folded, 20 in finally


def _plan_tier2(*keys):
    plan = _plan()
    object.__setattr__(plan, "tier2", frozenset(keys))
    return plan


def test_tier2_expands_selected_modules_in_order():
    from gest.core.install.registry import TIER2_MODULES, _tier2_steps
    assert _tier2_steps(_plan()) == []                   # empty by default
    labels = [s.label for s in _tier2_steps(_plan_tier2("sshd", "sysctl"))]
    assert labels == ["Emerge openssh", "Configure sshd", "Enable sshd at boot",
                      "Configure sysctl"]
    # module order follows TIER2_MODULES regardless of set iteration order
    assert TIER2_MODULES == ("sshd", "firewall", "sudo", "sysctl")


def test_tier2_step_markers_and_boundary():
    from gest.core.install.registry import _tier2_steps
    steps = {s.label: s for s in _tier2_steps(_plan_tier2("sshd", "firewall", "sudo", "sysctl"))}
    # emerges + service-enables run in the chroot; config writes are host-side seam
    assert steps["Emerge openssh"].chroot and steps["Enable sshd at boot"].chroot
    assert steps["Configure sshd"].target_aware and not steps["Configure sshd"].chroot
    assert steps["Configure sysctl"].target_aware
    # the chroot emerges are marker-gated (no cheap probe)
    assert steps["Emerge nftables"].key == "tier2_nftables"


def test_tier2_unknown_module_raises():
    from gest.core.install.registry import _tier2_steps
    with pytest.raises(ValueError, match="unknown tier-2"):
        _tier2_steps(_plan_tier2("bogus"))


# --- argv / chroot-boundary over a FakeExecutor -----------------------------

def _chroot_subset(reg):
    """PrepareChroot plus the chroot argv steps, in registry order."""
    return [s for s in reg if s.opens_chroot or s.chroot]


def test_chroot_steps_are_prefixed_and_bracketed_by_pseudofs():
    plan = _plan(user=UserSpec("alice", wheel=True))
    subset = _chroot_subset(build_registry(plan))
    # supply the root-password secret (never in the plan)
    next(s for s in subset if isinstance(s, SetRootPassword)).secret = lambda: "pw"

    fx = FakeExecutor()
    asyncio.run(run_install(_ctx(fx, plan=plan), subset))
    calls = fx.calls

    chroot_calls = [c for c in calls if c[:1] == ["chroot"]]
    assert chroot_calls, "expected chroot-wrapped argv"
    for c in chroot_calls:
        assert c[:2] == ["chroot", _ROOT]              # every chroot step is prefixed

    first = calls.index(chroot_calls[0])
    last = calls.index(chroot_calls[-1])
    # prepare_chroot's proc mount ran (host, un-prefixed) before the first chroot
    assert ["mount", "-t", "proc", "proc", f"{_ROOT}/proc"] in calls[:first]
    # teardown's lazy unmounts ran (finally) after the last chroot argv
    umounts = [i for i, c in enumerate(calls) if c[:1] == ["umount"]]
    assert umounts and min(umounts) > last
    # host argv is never chroot-prefixed
    for c in calls:
        if c[:1] in (["mount"], ["mkdir"], ["umount"]):
            assert c[:1] != ["chroot"]


def test_chroot_argv_content_matches_the_plan():
    plan = _plan(user=UserSpec("alice", wheel=True))
    subset = _chroot_subset(build_registry(plan))
    next(s for s in subset if isinstance(s, SetRootPassword)).secret = lambda: "pw"
    fx = FakeExecutor()
    asyncio.run(run_install(_ctx(fx, plan=plan), subset))
    inner = [c[2:] for c in fx.calls if c[:2] == ["chroot", _ROOT]]

    assert ["emerge", "--sync", "--color", "n"] in inner
    assert ["eselect", "profile", "set", "1"] in inner
    assert ["emerge", "--getbinpkg", "-uDN", "--color", "n", "@world"] in inner
    assert ["chpasswd"] in inner                        # password on stdin, not argv
    assert ["useradd", "--create-home", "--shell", "/bin/bash", "alice"] in inner
    assert ["gpasswd", "-a", "alice", "wheel"] in inner
    assert any(c[:1] == ["grub-install"] for c in inner)
    assert any(c[:1] == ["make"] and "-j2" in c for c in inner)


# --- resume: a satisfied (marker-set) step is skipped -----------------------

def test_marker_gated_step_is_skipped_when_marked():
    reg = build_registry(_plan())
    emerge = next(s for s in reg if isinstance(s, EmergeWorld))
    fx = FakeExecutor()
    ctx = _ctx(fx)
    ctx.state.mark(emerge)                              # marks key "emerge_world"
    assert asyncio.run(emerge.is_satisfied(ctx)) is True
    asyncio.run(run_install(ctx, [emerge]))
    assert fx.calls == []                               # nothing ran


def test_createuser_satisfied_when_no_user_requested():
    reg = build_registry(_plan(user=None))
    create = next(s for s in reg if isinstance(s, CreateUser))
    assert asyncio.run(create.is_satisfied(_ctx(FakeExecutor()))) is True


# --- config writes go to real files on the host (no D-Bus) ------------------

def test_config_step_writes_a_real_file_and_becomes_satisfied(tmp_path):
    root = str(tmp_path / "gentoo")
    fx = FakeExecutor()
    ctx = _ctx(fx, root=root)
    step = SetHostname()
    assert asyncio.run(step.is_satisfied(ctx)) is False
    asyncio.run(step.run(ctx))
    written = tmp_path / "gentoo/etc/conf.d/hostname"
    assert written.read_text() == 'hostname="gentoo"\n'
    assert fx.calls == []                               # host-side write, no executor/D-Bus
    assert asyncio.run(step.is_satisfied(ctx)) is True


def test_config_step_rejects_invalid_value(tmp_path):
    ctx = _ctx(FakeExecutor(), root=str(tmp_path / "g"))
    object.__setattr__(ctx.plan, "hostname", "bad host!")
    with pytest.raises(ValueError):
        asyncio.run(SetHostname().run(ctx))


# --- write_under_root -------------------------------------------------------

def test_write_under_root_atomic_mkdirs_and_returns_path(tmp_path):
    root = str(tmp_path / "mnt")
    path = write_under_root(root, "/etc/portage/make.conf", 'MAKEOPTS="-j2"\n')
    assert path == root + "/etc/portage/make.conf"
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == 'MAKEOPTS="-j2"\n'
    assert os.stat(path).st_mode & 0o777 == 0o644


def test_write_under_root_honours_mode(tmp_path):
    path = write_under_root(str(tmp_path / "mnt"), "/etc/secret", "x", mode=0o600)
    assert os.stat(path).st_mode & 0o777 == 0o600


# --- stage3 download_argv builder -------------------------------------------

def test_download_argv_prefers_wget_then_curl():
    assert stage3_commands.download_argv("https://m/f.txz", "/d/f.txz") == [
        "wget", "--progress=dot:giga", "-O", "/d/f.txz", "https://m/f.txz"]
    assert stage3_commands.download_argv("https://m/f", "/d/f", wget="") == [
        "curl", "-L", "--fail", "-o", "/d/f", "https://m/f"]
    assert stage3_commands.download_argv("u", "d", curl="/usr/bin/curl", wget="")[0] \
        == "/usr/bin/curl"
