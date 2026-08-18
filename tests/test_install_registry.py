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
    "Provision the HeDE desktop",
    "Install the HeDE desktop",
    "Clean up desktop binpkgs",
    "Set timezone and locale",
    "Set the hostname",
    "Set the console keymap",
    "Install kernel sources",
    "Build the kernel",
    "Install the bootloader",
    "Install the m1n1 boot stub",
    "Set the root password",
    "Create the user account",
    "Configure the network",
    "Enable the HeDE session",
]

# The six marker-gated steps (§6) and the one step that opens the chroot.
_MARKER_KEYS = {
    "Partition the disk": "partition",
    "Unpack the stage3 tarball": "unpack_stage3",
    "Sync the Portage tree": "sync_tree",
    "Emerge @world": "emerge_world",
    "Provision the HeDE desktop": "provision_desktop",
    "Install the HeDE desktop": "install_desktop",
    "Clean up desktop binpkgs": "cleanup_desktop_binpkgs",
    "Install kernel sources": "install_kernel_sources",
    "Build the kernel": "build_kernel",
    "Install the bootloader": "install_bootloader",
    "Install the m1n1 boot stub": "install_boot_stub",
    "Enable the HeDE session": "enable_desktop_session",
}
_CHROOT_LABELS = {
    "Sync the Portage tree", "Select the profile", "Emerge @world",
    "Install the HeDE desktop",
    "Install kernel sources", "Build the kernel", "Install the bootloader",
    "Install the m1n1 boot stub",
    "Set the root password", "Create the user account",
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
    assert [s.phase for s in reg[3:13]] == [Phase.BASE_SYSTEM] * 10  # +HeDE desktop (x3)
    assert [s.phase for s in reg[13:16]] == [Phase.CONFIGURE] * 3
    assert [s.phase for s in reg[16:20]] == [Phase.KERNEL_BOOT] * 4  # +kernel sources, +m1n1
    assert [s.phase for s in reg[20:23]] == [Phase.USERS_NETWORK] * 3
    assert [s.phase for s in reg[23:24]] == [Phase.FINISH]           # +HeDE session


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
    # base rows + 3 HeDE desktop steps + kernel-sources + enable-session + the
    # arm64-gated m1n1 boot stub (inert on x86)
    assert len(build_registry(_plan())) == 24


def test_boot_stub_step_is_arm64_gated():
    from gest.core.install.registry import InstallBootStub
    step = InstallBootStub()
    # amd64 (default plan): inert — no pipeline, and satisfied so the engine skips it
    amd = _ctx(FakeExecutor())
    assert step.build(amd) == []
    assert asyncio.run(step.is_satisfied(amd)) is True
    # arm64: emits the update-m1n1 write into the mounted ESP (efi_directory default /efi)
    plan = _plan()
    object.__setattr__(plan, "arch", "arm64")
    arm = _ctx(FakeExecutor(), plan=plan)
    steps = step.build(arm)
    assert [s.argv for s in steps] == [["update-m1n1", "/efi/m1n1/boot.bin"]]
    assert asyncio.run(step.is_satisfied(arm)) is False        # not yet done → runs


def _desktop_plan():
    plan = _plan()
    object.__setattr__(plan, "desktop", True)
    return plan


def test_desktop_steps_are_gated_on_plan_desktop():
    from gest.core.install.registry import CleanupDesktopBinpkgs, InstallDesktop
    for step in (InstallDesktop(), CleanupDesktopBinpkgs()):
        base = _ctx(FakeExecutor())                     # default plan → desktop=False
        assert step.build(base) == []                   # inert
        assert asyncio.run(step.is_satisfied(base)) is True


def test_install_desktop_emerges_usepkgonly_when_enabled():
    from gest.core.install.desktop import DESKTOP_ATOMS
    from gest.core.install.registry import InstallDesktop
    desk = _ctx(FakeExecutor(), plan=_desktop_plan())
    steps = InstallDesktop().build(desk)
    assert [s.argv for s in steps] == [
        ["emerge", "--usepkgonly", "--color", "n", *DESKTOP_ATOMS]]  # binary-only, offline
    assert asyncio.run(InstallDesktop().is_satisfied(desk)) is False


def test_cleanup_desktop_binpkgs_removes_target_pkgdir_when_enabled():
    from gest.core.install.registry import CleanupDesktopBinpkgs
    desk = _ctx(FakeExecutor(), plan=_desktop_plan())
    steps = CleanupDesktopBinpkgs().build(desk)
    assert [s.argv for s in steps] == [["rm", "-rf", f"{_ROOT}/var/cache/binpkgs"]]


def _patch_overlay_present(monkeypatch, present):
    # scope the patch to the overlay path only, so write_under_root's real fs ops work
    from gest.core.install import desktop, registry
    real = os.path.isdir
    monkeypatch.setattr(registry.os.path, "isdir",
                        lambda p: present if p == desktop.OVERLAY_LOCATION else real(p))


def test_provision_desktop_quickpkgs_and_seeds_overlay_when_present(tmp_path, monkeypatch):
    from gest.core.install.registry import ProvisionDesktop
    _patch_overlay_present(monkeypatch, True)
    root = str(tmp_path / "gentoo")
    fx = FakeExecutor()
    ctx = _ctx(fx, root=root, plan=_desktop_plan())
    step = ProvisionDesktop()
    assert asyncio.run(step.is_satisfied(ctx)) is False
    asyncio.run(step.run(ctx))
    # host-side (not chroot): quickpkg into the target pkgdir, then seed the overlay
    assert ["env", f"PKGDIR={root}/var/cache/binpkgs", "quickpkg",
            "--include-config=y", "@installed"] in fx.calls
    assert ["cp", "-a", "/var/db/repos/amphitheater",
            f"{root}/var/db/repos/amphitheater"] in fx.calls
    assert not any(c[:1] == ["chroot"] for c in fx.calls)       # host-side, never chrooted
    conf = tmp_path / "gentoo/etc/portage/repos.conf/amphitheater.conf"
    assert "sync-uri = https://github.com/k5blazerfl/Amphitheater" in conf.read_text()
    kw = tmp_path / "gentoo/etc/portage/package.accept_keywords/gest-hede"
    assert "gui-apps/hede ~amd64" in kw.read_text()             # ~arch for --usepkgonly
    assert asyncio.run(step.is_satisfied(ctx)) is True          # marked done


def test_provision_desktop_skips_overlay_seed_when_absent(tmp_path, monkeypatch):
    # the GeSI ISO can have an empty /var/db/repos — the copy must be skipped, not fail,
    # and the git-backed repos.conf must still be written (for day-2 sync).
    from gest.core.install.registry import ProvisionDesktop
    _patch_overlay_present(monkeypatch, False)
    root = str(tmp_path / "gentoo")
    fx = FakeExecutor()
    ctx = _ctx(fx, root=root, plan=_desktop_plan())
    asyncio.run(ProvisionDesktop().run(ctx))
    assert any(c[:3] == ["env", f"PKGDIR={root}/var/cache/binpkgs", "quickpkg"] for c in fx.calls)
    assert not any(c[:1] == ["cp"] for c in fx.calls)           # no overlay copy attempted
    conf = tmp_path / "gentoo/etc/portage/repos.conf/amphitheater.conf"
    assert "sync-uri = https://github.com/k5blazerfl/Amphitheater" in conf.read_text()
    kw = tmp_path / "gentoo/etc/portage/package.accept_keywords/gest-hede"
    assert "gui-apps/hede ~amd64" in kw.read_text()             # keywords written regardless


def test_provision_desktop_is_a_noop_for_base_gentoo():
    from gest.core.install.registry import ProvisionDesktop
    fx = FakeExecutor()
    ctx = _ctx(fx)                                              # desktop=False
    asyncio.run(ProvisionDesktop().run(ctx))
    assert fx.calls == []
    assert asyncio.run(ProvisionDesktop().is_satisfied(ctx)) is True


def test_enable_desktop_session_autologins_and_enables_greetd(tmp_path):
    from gest.core.install.registry import EnableDesktopSession
    plan = _plan(user=UserSpec("alice", wheel=True))
    object.__setattr__(plan, "desktop", True)
    root = str(tmp_path / "g")
    fx = FakeExecutor()
    ctx = _ctx(fx, root=root, plan=plan)
    step = EnableDesktopSession()
    assert asyncio.run(step.is_satisfied(ctx)) is False
    asyncio.run(step.run(ctx))
    cfg = (tmp_path / "g/etc/greetd/config.toml").read_text()
    assert 'user = "alice"' in cfg and "helm-session" in cfg
    inner = [c[2:] for c in fx.calls if c[:2] == ["chroot", _ROOT]]
    assert ["systemctl", "enable", "greetd"] in inner
    assert ["systemctl", "set-default", "graphical.target"] in inner
    assert asyncio.run(step.is_satisfied(ctx)) is True


def test_enable_desktop_session_is_a_noop_for_base_gentoo():
    from gest.core.install.registry import EnableDesktopSession
    fx = FakeExecutor()
    ctx = _ctx(fx)                                              # desktop=False
    asyncio.run(EnableDesktopSession().run(ctx))
    assert fx.calls == []
    assert asyncio.run(EnableDesktopSession().is_satisfied(ctx)) is True


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
    assert ["eselect", "profile", "set", "default/linux/amd64/23.0/systemd"] in inner
    assert ["emerge", "--getbinpkg", "-uDN", "--color", "n", "@world"] in inner
    # kernel sources emerged + /usr/src/linux selected before the build
    assert ["emerge", "--getbinpkg", "--color", "n", "--noreplace",
            "sys-kernel/gentoo-sources"] in inner
    assert ["eselect", "kernel", "set", "1"] in inner
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
    # both init formats: systemd /etc/hostname + OpenRC /etc/conf.d/hostname
    assert (tmp_path / "gentoo/etc/hostname").read_text() == "gentoo\n"
    assert (tmp_path / "gentoo/etc/conf.d/hostname").read_text() == 'hostname="gentoo"\n'
    assert fx.calls == []                               # host-side write, no executor/D-Bus
    assert asyncio.run(step.is_satisfied(ctx)) is True


def test_set_console_writes_both_vconsole_and_keymaps(tmp_path):
    from gest.core.install.registry import SetConsole
    root = str(tmp_path / "gentoo")
    ctx = _ctx(FakeExecutor(), root=root)
    object.__setattr__(ctx.plan, "keymap", "us")
    step = SetConsole()
    assert asyncio.run(step.is_satisfied(ctx)) is False
    asyncio.run(step.run(ctx))
    assert (tmp_path / "gentoo/etc/vconsole.conf").read_text() == "KEYMAP=us\n"   # systemd
    assert 'keymap="us"' in (tmp_path / "gentoo/etc/conf.d/keymaps").read_text()  # OpenRC
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
