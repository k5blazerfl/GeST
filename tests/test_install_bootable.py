"""CI-safe tests for installer step 4c: the executor stdin seam and the minimal
bootable registry. Driven by FakeExecutor — no subprocess, no mounts, no network."""

import asyncio

from gest.core.bootloader.install import InstallConfig
from gest.core.disk import mount as disk_mount
from gest.core.disk import provision
from gest.core.exec.chroot import ChrootExecutor
from gest.core.exec.executor import FakeExecutor
from gest.core.exec.steps import Step, run_steps
from gest.core.install.context import InstallContext, StateStore
from gest.core.install.engine import run_install
from gest.core.install.plan import InstallPlan
from gest.core.install.registry import (
    SetRootPassword,
    build_minimal_registry,
    build_registry,
)
from gest.core.kernel.build import BuildConfig
from gest.core.stage3.model import Stage3Selection

_ROOT = "/mnt/gentoo"


def _plan():
    disk = provision.uefi_plan("sda", "512M", "8G", "ext4")
    return InstallPlan(
        disk=disk,
        mount=disk_mount.derive_mount_plan(disk, _ROOT),
        stage3=Stage3Selection(
            url="https://mirror/stage3.tar.xz", filename="stage3.tar.xz", size=1,
            digests_url="https://mirror/stage3.tar.xz.DIGESTS",
            signature_url="https://mirror/stage3.tar.xz.asc"),
        kernel=BuildConfig(method="make", jobs=2),
        bootloader=InstallConfig(firmware="uefi"),
        hostname="gentoo", timezone="UTC", locale="en_US.UTF-8", keymap="us",
    )


def _ctx(executor, plan=None):
    return InstallContext(
        root=_ROOT, host=executor, target=ChrootExecutor(executor, _ROOT),
        state=StateStore(), plan=plan or _plan())


# --- the executor stdin seam ------------------------------------------------

def test_step_stdin_threads_through_run_steps():
    fx = FakeExecutor()
    asyncio.run(run_steps([
        Step("no stdin", ["a"]),
        Step("with stdin", ["b"], stdin="payload\n"),
    ], fx))
    assert fx.calls == [["a"], ["b"]]
    assert fx.stdins == [None, "payload\n"]        # parallel to calls; secret not in argv


def test_chroot_executor_forwards_stdin():
    fx = FakeExecutor()
    ex = ChrootExecutor(fx, _ROOT)
    asyncio.run(ex.run(["chpasswd"], stdin="root:pw\n"))
    assert fx.calls == [["chroot", _ROOT, "chpasswd"]]
    assert fx.stdins == ["root:pw\n"]


def test_step_default_stdin_is_none():
    assert Step("x", ["y"]).stdin is None          # backward-compatible default


# --- SetRootPassword pipes the secret, never puts it in argv -----------------

def test_set_root_password_delivers_secret_on_stdin_in_chroot():
    fx = FakeExecutor()
    step = SetRootPassword()
    step.secret = lambda: "hunter2"
    asyncio.run(run_install(_ctx(fx), [step]))
    # ran chpasswd inside the target…
    assert fx.calls == [["chroot", _ROOT, "chpasswd"]]
    # …with the password on stdin, and NOT anywhere in the argv
    assert fx.stdins == ["root:hunter2\n"]
    assert all("hunter2" not in tok for call in fx.calls for tok in call)


def test_set_root_password_without_secret_raises():
    fx = FakeExecutor()
    step = SetRootPassword()                        # no secret set
    try:
        asyncio.run(run_install(_ctx(fx), [step]))
    except ValueError as exc:
        assert "secret" in str(exc)
    else:
        raise AssertionError("expected ValueError when no secret is supplied")


# --- the minimal bootable registry ------------------------------------------

_MINIMAL_LABELS = [
    "Partition the disk", "Make filesystems", "Mount the target",
    "Unpack the stage3 tarball", "Generate /etc/fstab", "Write make.conf",
    "Prepare the chroot", "Sync the Portage tree", "Select the profile",
    "Emerge @world", "Install kernel sources", "Stage the kernel config",
    "Build the kernel", "Install the bootloader",
    "Install the m1n1 boot stub", "Set the root password",
]


def test_minimal_registry_is_the_boot_critical_order():
    reg = build_minimal_registry(_plan())
    assert [s.label for s in reg] == _MINIMAL_LABELS


def test_minimal_is_a_strict_subset_of_the_full_registry():
    full = {s.label for s in build_registry(_plan())}
    minimal = {s.label for s in build_minimal_registry(_plan())}
    assert minimal < full                           # strict subset
    # the dropped steps are exactly the HeDE desktop (provision/install/cleanup) +
    # GPU drivers/firmware (not boot-critical) + day-1 niceties + optional
    # user/network (a bootable base system needs none)
    assert full - minimal == {
        "Provision the HeDE desktop", "Install the HeDE desktop",
        "Clean up desktop binpkgs", "Enable the HeDE session",
        "Install GPU drivers & firmware",
        "Set timezone and locale", "Set the hostname", "Set the console keymap",
        "Create the user account", "Set the user password",
        "Configure the network", "Configure the clock",
    }
    # everything the minimal set keeps is present in the full set, same relative order
    full_order = [s.label for s in build_registry(_plan())]
    assert [s.label for s in build_minimal_registry(_plan())] == \
        [lbl for lbl in full_order if lbl in minimal]


def test_minimal_root_password_secret_is_wired():
    reg = build_minimal_registry(_plan(), root_secret=lambda: "pw")
    root_pw = reg[-1]
    assert isinstance(root_pw, SetRootPassword)
    assert root_pw.secret() == "pw"


def test_minimal_end_to_end_chroot_boundary_and_teardown():
    # Run the hermetic subset — drop the steps that touch real block devices or
    # do real file/network I/O (partition/mkfs/mount, stage3 download, fstab &
    # make.conf writes); prepare_chroot and the chroot steps run purely through
    # the FakeExecutor. Asserts the chroot boundary + teardown + the piped password.
    fx = FakeExecutor()
    reg = build_minimal_registry(_plan(), root_secret=lambda: "s3cret")
    drop = {"Partition the disk", "Make filesystems", "Mount the target",
            "Unpack the stage3 tarball", "Generate /etc/fstab", "Write make.conf"}
    steps = [s for s in reg if s.label not in drop]
    asyncio.run(run_install(_ctx(fx), steps))

    calls = fx.calls
    # every chroot step is prefixed; the host steps are not
    chpasswd = next(c for c in calls if c[-1] == "chpasswd")
    assert chpasswd[:2] == ["chroot", _ROOT]
    # prepare_chroot's proc mount ran before the first chroot command…
    proc_mount = ["mount", "-t", "proc", "proc", f"{_ROOT}/proc"]
    first_chroot = min(i for i, c in enumerate(calls) if c[:1] == ["chroot"])
    assert calls.index(proc_mount) < first_chroot
    # …and teardown's unmounts ran after it (engine finally)
    last_chroot = max(i for i, c in enumerate(calls) if c[:1] == ["chroot"])
    assert any(c[:1] == ["umount"] and i > last_chroot for i, c in enumerate(calls))
    # the password was piped, never in argv
    assert "root:s3cret\n" in fx.stdins
    assert all("s3cret" not in tok for c in calls for tok in c)
