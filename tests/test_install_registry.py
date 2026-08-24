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
from gest.core.exec.steps import StepError
from gest.core.install.context import InstallContext, StateStore
from gest.core.install.engine import run_install
from gest.core.install.plan import InstallPlan, Phase, UserSpec
from gest.core.install.registry import (
    CreateUser,
    EmergeWorld,
    SetHostname,
    SetRootPassword,
    SyncTree,
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
    "Provision the Helm Desktop Environment",
    "Install the Helm Desktop Environment",
    "Clean up desktop binpkgs",
    "Set timezone and locale",
    "Generate the locale",
    "Set the hostname",
    "Set the console keymap",
    "Install kernel sources",
    "Stage the kernel config",
    "Build the kernel",
    "Install GPU drivers & firmware",
    "Install the bootloader",
    "Install the m1n1 boot stub",
    "Set the root password",
    "Create user accounts",
    "Set user passwords",
    "Configure the network",
    "Enable the Helm Desktop Environment session",
    "Configure the clock",
]

# The six marker-gated steps (§6) and the one step that opens the chroot.
_MARKER_KEYS = {
    "Partition the disk": "partition",
    "Unpack the stage3 tarball": "unpack_stage3",
    "Sync the Portage tree": "sync_tree",
    "Emerge @world": "emerge_world",
    "Provision the Helm Desktop Environment": "provision_desktop",
    "Install the Helm Desktop Environment": "install_desktop",
    "Clean up desktop binpkgs": "cleanup_desktop_binpkgs",
    "Generate the locale": "generate_locale",
    "Install kernel sources": "install_kernel_sources",
    "Stage the kernel config": "stage_kernel_config",
    "Build the kernel": "build_kernel",
    "Install GPU drivers & firmware": "install_gpu_drivers",
    "Install the bootloader": "install_bootloader",
    "Install the m1n1 boot stub": "install_boot_stub",
    "Configure the network": "configure_network",
    "Enable the Helm Desktop Environment session": "enable_desktop_session",
    "Configure the clock": "configure_clock",
}
_CHROOT_LABELS = {
    "Sync the Portage tree", "Select the profile", "Emerge @world",
    "Install the Helm Desktop Environment", "Generate the locale",
    "Install kernel sources", "Build the kernel", "Install the bootloader",
    "Install the m1n1 boot stub",
    "Set the root password", "Create user accounts", "Set user passwords",
    "Configure the clock",
}
_PHASE_ORDER = list(Phase)


def _plan(*, user=None, users=()):
    if user is not None:                       # compat shim for single-user call sites
        users = (user,)
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
        users=tuple(users),
    )


def _ctx(executor, root=_ROOT, *, plan=None, target_root=_ROOT):
    return InstallContext(
        root=root, host=executor, target=ChrootExecutor(executor, target_root),
        state=StateStore(), plan=plan or _plan())


# --- SyncTree retry + webrsync fallback -------------------------------------

def _sync_step():
    step = SyncTree()
    step._BACKOFF = 0          # no real sleeps in tests
    return step


def _is_sync(argv):        # argv is chroot-wrapped: ["chroot", root, "emerge", "--sync", …]
    return "--sync" in argv


def _is_webrsync(argv):
    return "emerge-webrsync" in argv


def test_sync_retries_then_succeeds_without_webrsync():
    calls = {"sync": 0}

    def code_for(argv):
        if _is_sync(argv):
            calls["sync"] += 1
            return 0 if calls["sync"] >= 2 else 1     # fail once, then take
        return 0

    ex = FakeExecutor(code_for)
    asyncio.run(_sync_step().run(_ctx(ex)))
    assert calls["sync"] == 2
    assert not any(_is_webrsync(c) for c in ex.calls)  # never needed the fallback


def test_sync_falls_back_to_webrsync_after_retries():
    def code_for(argv):
        return 0 if _is_webrsync(argv) else 1          # --sync always fails

    ex = FakeExecutor(code_for)
    asyncio.run(_sync_step().run(_ctx(ex)))            # must NOT raise
    assert sum(_is_sync(c) for c in ex.calls) == SyncTree._RETRIES
    assert any(_is_webrsync(c) for c in ex.calls)      # fell back


def test_sync_raises_when_both_paths_fail():
    ex = FakeExecutor(lambda _argv: 1)                 # everything fails
    with pytest.raises(StepError):
        asyncio.run(_sync_step().run(_ctx(ex)))
    assert sum(_is_sync(c) for c in ex.calls) == SyncTree._RETRIES
    assert any(_is_webrsync(c) for c in ex.calls)      # tried the fallback too


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
    assert [s.phase for s in reg[13:17]] == [Phase.CONFIGURE] * 4    # +Generate the locale
    # KERNEL_BOOT: sources, stage-config, build, gpu-drivers, bootloader, m1n1
    assert [s.phase for s in reg[17:23]] == [Phase.KERNEL_BOOT] * 6
    assert [s.phase for s in reg[23:27]] == [Phase.USERS_NETWORK] * 4  # +user password
    assert [s.phase for s in reg[27:29]] == [Phase.FINISH] * 2       # HeDE session + clock


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
    # base rows + 3 HeDE desktop steps + kernel-sources + stage-kernel-config +
    # gpu-drivers + enable-session + configure-clock + the arm64-gated m1n1 boot stub
    assert len(build_registry(_plan())) == 29


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


def _genkernel_plan(**kernel_kw):
    import dataclasses
    plan = _plan()
    object.__setattr__(plan, "kernel",
                       dataclasses.replace(plan.kernel, method="genkernel", **kernel_kw))
    return plan


def test_install_kernel_sources_adds_genkernel_for_the_genkernel_method():
    from gest.core.install.registry import InstallKernelSources
    # make method (default test plan): gentoo-sources only, no genkernel
    base = InstallKernelSources().build(_ctx(FakeExecutor()))
    assert not any("sys-kernel/genkernel" in s.argv for s in base)
    # genkernel method: also emerges genkernel — normally, WITHOUT the old
    # USE=-firmware hack (linux-firmware is now license-permitted via ACCEPT_LICENSE).
    steps = InstallKernelSources().build(_ctx(FakeExecutor(), plan=_genkernel_plan()))
    by_label = {s.label: s.argv for s in steps}
    assert "sys-kernel/gentoo-sources" in by_label["emerge gentoo-sources"]
    gk = by_label["emerge genkernel"]
    assert "sys-kernel/genkernel" in gk
    assert "env" not in gk and not any("USE=" in a for a in gk)   # no -firmware hack
    assert steps[-1].argv == ["eselect", "kernel", "set", "1"]   # select /usr/src/linux last


def test_install_bootloader_emerges_grub_and_efibootmgr_first():
    from gest.core.install.registry import InstallBootloader
    steps = InstallBootloader().build(_ctx(FakeExecutor()))       # default plan → uefi
    first = steps[0].argv
    assert first[:2] == ["env", "GRUB_PLATFORMS=efi-64"]          # build the efi platform
    assert "sys-boot/grub" in first and "sys-boot/efibootmgr" in first
    assert any(s.argv and s.argv[0] == "grub-install" for s in steps)  # then install GRUB


def test_stage_kernel_config_writes_the_bundled_virtio_config(tmp_path):
    from gest.core.install.registry import StageKernelConfig
    from gest.core.kernel import config as kconfig
    root = str(tmp_path / "mnt")
    os.makedirs(root)
    plan = _genkernel_plan(kernel_config=kconfig.TARGET_KERNEL_CONFIG)
    object.__setattr__(plan, "arch", "amd64")
    ctx = _ctx(FakeExecutor(), root=root, plan=plan)
    step = StageKernelConfig()
    assert asyncio.run(step.is_satisfied(ctx)) is False           # config set, not yet done
    asyncio.run(step.run(ctx))
    written = root + kconfig.TARGET_KERNEL_CONFIG
    assert os.path.isfile(written)
    with open(written) as fh:
        assert "CONFIG_VIRTIO_BLK=y" in fh.read()                 # the fix: virtio built in
    # inert when no config is set (make method / arch with none bundled)
    inert = _ctx(FakeExecutor())
    assert asyncio.run(StageKernelConfig().is_satisfied(inert)) is True


def test_assemble_sets_the_kernel_config_for_genkernel_amd64():
    from gest.core.install.assemble import InstallSelections, assemble_plan
    from gest.core.kernel import config as kconfig
    from gest.core.stage3.model import Stage3Selection
    stage3 = Stage3Selection(url="https://m/s.tar.xz", filename="s.tar.xz", size=1,
                             digests_url="https://m/s.DIGESTS", signature_url="https://m/s.asc")
    # default amd64 systemd variant + genkernel → the shipped virtio config is wired
    plan = assemble_plan(
        InstallSelections(disk="vda", kernel_method="genkernel", root_password="x"), stage3)
    assert plan.arch == "amd64"
    assert plan.kernel.kernel_config == kconfig.TARGET_KERNEL_CONFIG


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


def test_configure_network_desktop_installs_and_enables_networkmanager(tmp_path):
    from gest.core.install.registry import ConfigureNetwork
    ex = FakeExecutor(lambda _a: 0)
    ctx = _ctx(ex, root=str(tmp_path), plan=_desktop_plan())   # hostname "gentoo"
    asyncio.run(ConfigureNetwork().run(ctx))
    cmds = [" ".join(c) for c in ex.calls]
    assert any("emerge" in c and "net-misc/networkmanager" in c for c in cmds)
    assert any("systemctl enable NetworkManager" in c for c in cmds)
    # /etc/hosts carries the machine's own name (no more netifrc)
    hosts_txt = (tmp_path / "etc/hosts").read_text()
    assert "127.0.1.1\tgentoo" in hosts_txt
    assert not (tmp_path / "etc/conf.d/net").exists()


def test_configure_network_base_uses_systemd_networkd(tmp_path):
    from gest.core.install.registry import ConfigureNetwork
    ex = FakeExecutor(lambda _a: 0)
    ctx = _ctx(ex, root=str(tmp_path), plan=_plan())           # desktop=False
    asyncio.run(ConfigureNetwork().run(ctx))
    cmds = [" ".join(c) for c in ex.calls]
    assert any("systemctl enable systemd-networkd" in c for c in cmds)
    assert any("systemctl enable systemd-resolved" in c for c in cmds)
    assert "DHCP=yes" in (tmp_path / "etc/systemd/network/20-gest.network").read_text()
    assert os.readlink(tmp_path / "etc/resolv.conf") == \
        "/run/systemd/resolve/stub-resolv.conf"
    assert not any("networkmanager" in c for c in cmds)         # no NM on a base install


def test_install_desktop_uses_binpkgs_when_present(tmp_path):
    from gest.core.install.desktop import DESKTOP_ATOMS
    from gest.core.install.registry import InstallDesktop
    # desktop ISO: a quickpkg'd hede binpkg sits in the target PKGDIR → binary-only
    pkg = tmp_path / "var/cache/binpkgs/gui-apps"
    pkg.mkdir(parents=True)
    (pkg / "hede-0.7.0-1.gpkg.tar").write_text("x")
    desk = _ctx(FakeExecutor(), root=str(tmp_path), plan=_desktop_plan())
    steps = InstallDesktop().build(desk)
    assert [s.argv for s in steps] == [
        ["emaint", "binhost", "--fix"],                                # refresh index (fixups)
        ["emerge", "--usepkgonly", "--color", "n", *DESKTOP_ATOMS]]    # binary-only, offline
    assert asyncio.run(InstallDesktop().is_satisfied(desk)) is False


def test_install_desktop_git_syncs_overlay_when_unseeded_and_no_binpkgs(tmp_path):
    from gest.core.install.desktop import DESKTOP_ATOMS
    from gest.core.install.registry import InstallDesktop
    # CLI ISO, overlay not seeded → install git, git-sync the overlay, emerge (network)
    desk = _ctx(FakeExecutor(), root=str(tmp_path), plan=_desktop_plan())
    steps = InstallDesktop().build(desk)
    assert [s.argv for s in steps] == [
        ["emerge", "--getbinpkg", "--color", "n", "dev-vcs/git"],
        ["emaint", "sync", "-r", "amphitheater"],
        ["emerge", "--getbinpkg", "--update", "--deep", "--newuse", "--color", "n",
         *DESKTOP_ATOMS]]


def test_install_desktop_skips_sync_when_overlay_seeded_but_no_binpkgs(tmp_path):
    from gest.core.install.desktop import DESKTOP_ATOMS
    from gest.core.install.registry import InstallDesktop
    # overlay content present (seeded) but no binpkgs → no git/sync, just emerge
    (tmp_path / "var/db/repos/amphitheater").mkdir(parents=True)
    desk = _ctx(FakeExecutor(), root=str(tmp_path), plan=_desktop_plan())
    steps = InstallDesktop().build(desk)
    assert [s.argv for s in steps] == [
        ["emerge", "--getbinpkg", "--update", "--deep", "--newuse", "--color", "n",
         *DESKTOP_ATOMS]]


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


def test_writefstab_is_not_satisfied_by_the_stage3_template(tmp_path):
    # The stage3 ships an all-commented /etc/fstab. A bare exists() check marked the
    # step done → it was SKIPPED every install → no root entry → read-only root →
    # logind/machine-id/desktop all break. It must only be satisfied by a VALID
    # generated fstab (bug #17).
    from gest.core.install.registry import WriteFstab
    root = str(tmp_path / "mnt")
    os.makedirs(os.path.join(root, "etc"))
    ctx = _ctx(FakeExecutor(), root=root)
    step = WriteFstab()
    fstab = os.path.join(root, "etc", "fstab")
    assert asyncio.run(step.is_satisfied(ctx)) is False          # absent → run it
    with open(fstab, "w") as fh:                                 # stage3 template (all commented)
        fh.write("# <fs> <mountpoint> <type> <opts> <dump> <pass>\n"
                 "#UUID=58e72203-57d1-4497-81ad-97655bd56494 / xfs defaults 0 1\n")
    assert asyncio.run(step.is_satisfied(ctx)) is False          # template → still run it
    with open(fstab, "w") as fh:                                 # a real generated fstab
        fh.write("UUID=1bebf1f8-dc6b-4a25-a848-45a5928edec2\t/\text4\tdefaults\t0 1\n")
    assert asyncio.run(step.is_satisfied(ctx)) is True           # valid → done


def test_createuser_satisfied_when_no_user_requested():
    reg = build_registry(_plan(user=None))
    create = next(s for s in reg if isinstance(s, CreateUser))
    assert asyncio.run(create.is_satisfied(_ctx(FakeExecutor()))) is True


def test_createuser_adds_desktop_device_groups_only_for_a_desktop_install():
    # a desktop autologin user needs video/input/audio/render (best-effort per group)
    desk = _plan(user=UserSpec("alice", wheel=True))
    object.__setattr__(desk, "desktop", True)
    grp = [s.argv for s in CreateUser().build(_ctx(FakeExecutor(), plan=desk))
           if s.argv and s.argv[0] == "sh"]
    assert grp and all(g in grp[0][-1] for g in ("video", "input", "audio", "render"))
    assert "getent group" in grp[0][-1]                      # best-effort: skip missing groups
    # a base (non-desktop) install gets wheel only, no device-group step
    base = _plan(user=UserSpec("alice", wheel=True))          # desktop=False default
    assert not any(s.argv and s.argv[0] == "sh"
                   for s in CreateUser().build(_ctx(FakeExecutor(), plan=base)))


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


# --- wizard P2: admin model steps + make.conf renders ------------------------

def _admin_plan(**kw):
    import dataclasses
    return dataclasses.replace(_plan(user=UserSpec(name="captain")), **kw)


def test_traditional_admin_adds_no_escalation_steps():
    labels = [s.label for s in build_registry(_plan())]
    assert "Emerge sudo" not in labels and "Lock the root account" not in labels


def test_sudo_augmented_adds_wheel_rule_but_no_lock():
    reg = build_registry(_admin_plan(admin_model="sudo-augmented", escalator="sudo"))
    labels = [s.label for s in reg]
    assert "Emerge sudo" in labels and "Configure sudo (wheel)" in labels
    assert "Lock the root account" not in labels


def test_rootless_sudo_locks_root_last_and_phases_hold():
    reg = build_registry(_admin_plan(admin_model="rootless", escalator="sudo"))
    labels = [s.label for s in reg]
    assert "Configure sudo (wheel)" in labels
    assert labels[-1] == "Lock the root account"        # after escalator + user
    idx = [list(Phase).index(s.phase) for s in reg]
    assert idx == sorted(idx)                            # non-decreasing (FINISH)


def test_rootless_doas_uses_doas():
    reg = build_registry(_admin_plan(admin_model="rootless", escalator="doas"))
    labels = [s.label for s in reg]
    assert "Emerge doas" in labels and "Configure doas (wheel)" in labels
    assert "Emerge sudo" not in labels
    assert labels[-1] == "Lock the root account"


async def test_write_makeconf_renders_license_use_and_overrides(tmp_path, monkeypatch):
    import dataclasses

    from gest.core.hwflags import detect as hwdetect
    from gest.core.install import capabilities
    from gest.core.install.registry import WriteMakeConf
    monkeypatch.setattr(hwdetect, "detect_cpu_flags", lambda *a, **k: [])
    use = capabilities.resolve_global_use({"bluetooth"})
    plan = dataclasses.replace(
        _plan(), license="redistributable", global_use=use, binary_pref=True,
        make_conf_overrides=(("ACCEPT_KEYWORDS", "~amd64"),))
    ctx = _ctx(FakeExecutor(), root=str(tmp_path), plan=plan)
    await WriteMakeConf().run(ctx)
    text = (tmp_path / "etc/portage/make.conf").read_text()
    assert "ACCEPT_LICENSE" in text and "@BINARY-REDISTRIBUTABLE" in text
    assert "bluetooth" in text and "USE=" in text
    assert "~amd64" in text                              # raw override, overlaid last
    assert "-march=native" not in text                  # binary_pref → no CPU tuning


async def test_write_makeconf_tunes_cpu_on_source_builds(tmp_path, monkeypatch):
    import dataclasses

    from gest.core.hwflags import detect as hwdetect
    from gest.core.install.registry import WriteMakeConf
    monkeypatch.setattr(hwdetect, "detect_cpu_flags", lambda *a, **k: [])
    plan = dataclasses.replace(_plan(), binary_pref=False)
    ctx = _ctx(FakeExecutor(), root=str(tmp_path), plan=plan)
    await WriteMakeConf().run(ctx)
    text = (tmp_path / "etc/portage/make.conf").read_text()
    assert "-march=native" in text and "target-cpu=native" in text


def test_configure_clock_chrony_installs_ntp_and_utc_rtc():
    import dataclasses

    from gest.core.install.registry import ConfigureClock
    plan = dataclasses.replace(_plan(), clock="chrony")
    steps = ConfigureClock().build(_ctx(FakeExecutor(), plan=plan))
    blob = " ".join(" ".join(s.argv) for s in steps)
    assert "UTC" in blob and "net-misc/chrony" in blob and "chronyd" in blob


def test_configure_clock_local_sets_local_rtc_no_ntp():
    import dataclasses

    from gest.core.install.registry import ConfigureClock
    plan = dataclasses.replace(_plan(), clock="local")
    steps = ConfigureClock().build(_ctx(FakeExecutor(), plan=plan))
    blob = " ".join(" ".join(s.argv) for s in steps)
    assert "LOCAL" in blob and "chrony" not in blob


def test_createuser_builds_a_step_set_per_user():
    p = _plan(users=(UserSpec(name="alice", wheel=True),
                     UserSpec(name="bob", wheel=False)))
    steps = CreateUser().build(_ctx(FakeExecutor(), plan=p))
    labels = " | ".join(s.label for s in steps)
    assert "create user alice" in labels and "create user bob" in labels
    assert "add alice to wheel" in labels
    assert "add bob to wheel" not in labels          # bob isn't an admin


def test_set_user_passwords_gated_and_fed_on_stdin():
    from gest.core.install.plan import UserSpec
    from gest.core.install.registry import SetUserPassword
    step = SetUserPassword()
    step.secrets = {"captain": lambda: "pw", "guest": lambda: "gg"}
    # no users → no-op + satisfied
    p0 = _plan()
    assert step.build(_ctx(FakeExecutor(), plan=p0)) == []
    assert asyncio.run(step.is_satisfied(_ctx(FakeExecutor(), plan=p0))) is True
    # two users, one WITHOUT set_password → one chpasswd step per set_password user;
    # each password rides stdin, not argv, keyed by name
    p1 = _plan(users=(UserSpec(name="captain", set_password=True),
                      UserSpec(name="guest", set_password=False)))
    steps = step.build(_ctx(FakeExecutor(), plan=p1))
    assert len(steps) == 1
    assert "captain:pw" in steps[0].stdin and "pw" not in " ".join(steps[0].argv)
    assert asyncio.run(step.is_satisfied(_ctx(FakeExecutor(), plan=p1))) is False
    # every user WITHOUT set_password → skipped/satisfied
    p2 = _plan(user=UserSpec(name="captain", set_password=False))
    assert step.build(_ctx(FakeExecutor(), plan=p2)) == []
    assert asyncio.run(step.is_satisfied(_ctx(FakeExecutor(), plan=p2))) is True


def test_set_user_passwords_missing_secret_raises():
    from gest.core.install.plan import UserSpec
    from gest.core.install.registry import SetUserPassword
    step = SetUserPassword()                      # no secrets wired
    p = _plan(user=UserSpec(name="captain", set_password=True))
    with pytest.raises(ValueError, match="captain"):
        step.build(_ctx(FakeExecutor(), plan=p))
