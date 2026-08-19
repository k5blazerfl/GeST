"""Tests for GPU driver + firmware install support.

Covers the pure ``gpu.py`` builders, the ``assemble`` → ``GpuSpec`` mapping and the
``lspci`` auto-detect (``resolve_gpu``), ``VIDEO_CARDS`` landing in make.conf, and
the ``InstallGpuDrivers`` step (firmware always; the NVIDIA proprietary stack —
driver + license + modprobe.d modeset/blacklist — when requested). Hermetic: a
FakeExecutor + tmp_path, no real emerge/lspci.
"""

import asyncio
import os
from pathlib import Path

from gest.core.bootloader.install import InstallConfig
from gest.core.disk import mount as disk_mount
from gest.core.disk import provision
from gest.core.exec.chroot import ChrootExecutor
from gest.core.exec.executor import FakeExecutor
from gest.core.install import gpu
from gest.core.install.assemble import InstallSelections, assemble_plan, resolve_gpu
from gest.core.install.context import InstallContext, StateStore
from gest.core.install.plan import GpuSpec, InstallPlan
from gest.core.install.registry import InstallGpuDrivers, WriteMakeConf
from gest.core.kernel.build import BuildConfig
from gest.core.stage3.model import Stage3Selection

_ROOT = "/mnt/gentoo"
_STAGE3 = Stage3Selection(
    url="https://m/s.tar.xz", filename="s.tar.xz", size=1,
    digests_url="https://m/s.DIGESTS", signature_url="https://m/s.asc")


def _plan(gpu_spec: GpuSpec | None = None) -> InstallPlan:
    # The mount plan targets the guarded /mnt/gentoo; the on-disk root a step writes
    # to is ctx.root (a tmp dir), set separately in _ctx.
    disk = provision.uefi_plan("sda", "512M", "8G", "ext4")
    return InstallPlan(
        disk=disk, mount=disk_mount.derive_mount_plan(disk, _ROOT), stage3=_STAGE3,
        kernel=BuildConfig(method="make", jobs=2), bootloader=InstallConfig(firmware="uefi"),
        hostname="gentoo", timezone="UTC", locale="en_US.UTF-8", keymap="us",
        gpu=gpu_spec or GpuSpec())


def _ctx(fx, root, plan):
    # ChrootExecutor guards its target root, so it uses the valid /mnt/gentoo; file
    # writes go to ctx.root (the tmp dir). Chroot argv is thus ["chroot", _ROOT, ...].
    return InstallContext(root=root, host=fx, target=ChrootExecutor(fx, _ROOT),
                          state=StateStore(), plan=plan)


def _lspci(*lines):
    return lambda argv: (0, "\n".join(lines))


# --- pure builders ----------------------------------------------------------

def test_video_cards_value():
    assert gpu.video_cards_value(GpuSpec(video_cards=("amdgpu", "radeonsi"))) == "amdgpu radeonsi"
    assert gpu.video_cards_value(GpuSpec()) == ""


def test_driver_atoms_firmware_only_without_nvidia():
    assert gpu.driver_atoms(GpuSpec(video_cards=("amdgpu",))) == ["sys-kernel/linux-firmware"]


def test_driver_atoms_add_nvidia_when_proprietary():
    spec = GpuSpec(video_cards=("nvidia",), nvidia_proprietary=True)
    assert gpu.driver_atoms(spec) == ["sys-kernel/linux-firmware", "x11-drivers/nvidia-drivers"]


def test_package_use_kernel_open_only_for_nvidia():
    on = gpu.package_use(
        GpuSpec(video_cards=("nvidia",), nvidia_proprietary=True, kernel_open=True))
    assert "x11-drivers/nvidia-drivers kernel-open" in on
    # off, or requested without the proprietary stack → nothing
    assert gpu.package_use(GpuSpec(video_cards=("nvidia",), nvidia_proprietary=True)) == ""
    assert gpu.package_use(GpuSpec(video_cards=("amdgpu",), kernel_open=True)) == ""


def test_package_license_accepts_firmware_and_optionally_nvidia():
    base = gpu.package_license(GpuSpec(video_cards=("amdgpu",)))
    assert "sys-kernel/linux-firmware linux-fw-redistributable" in base
    assert "NVIDIA-r2" not in base
    nv = gpu.package_license(GpuSpec(video_cards=("nvidia",), nvidia_proprietary=True))
    assert "x11-drivers/nvidia-drivers NVIDIA-r2" in nv


def test_modprobe_conf_enables_kms_and_blacklists_nouveau():
    conf = gpu.modprobe_conf()
    assert "blacklist nouveau" in conf
    assert "options nvidia_drm modeset=1 fbdev=1" in conf


def test_kernel_cmdline_nvidia_only():
    nv = gpu.kernel_cmdline(GpuSpec(video_cards=("nvidia",), nvidia_proprietary=True))
    assert "modprobe.blacklist=nouveau" in nv and "nvidia_drm.modeset=1" in nv
    assert gpu.kernel_cmdline(GpuSpec(video_cards=("amdgpu",))) == ""


def test_apply_gpu_cmdline_appends_and_is_idempotent():
    spec = GpuSpec(video_cards=("nvidia",), nvidia_proprietary=True)
    out = gpu.apply_gpu_cmdline('GRUB_CMDLINE_LINUX="rootflags=x"\n', spec)
    line = next(ln for ln in out.splitlines() if ln.startswith("GRUB_CMDLINE_LINUX="))
    assert "rootflags=x" in line and "nvidia_drm.modeset=1" in line
    # re-running does not double the args
    assert gpu.apply_gpu_cmdline(out, spec) == out


def test_apply_gpu_cmdline_adds_key_when_absent():
    out = gpu.apply_gpu_cmdline("# empty grub default\n",
                                GpuSpec(video_cards=("nvidia",), nvidia_proprietary=True))
    assert 'GRUB_CMDLINE_LINUX="' in out and "nvidia_drm.modeset=1" in out


def test_apply_gpu_cmdline_noop_for_non_nvidia():
    body = 'GRUB_CMDLINE_LINUX=""\n'
    assert gpu.apply_gpu_cmdline(body, GpuSpec(video_cards=("amdgpu",))) == body


def test_resolve_gpu_hybrid_amd_igpu_plus_nvidia_dgpu():
    # the 9900X3D has an RDNA2 iGPU alongside the 4070 Ti Super — both must land in
    # VIDEO_CARDS, and the presence of NVIDIA still opts into the proprietary stack.
    spec = resolve_gpu(_lspci(
        "05:00.0 VGA compatible controller: Advanced Micro Devices [AMD/ATI] Raphael",
        "01:00.0 VGA compatible controller: NVIDIA Corporation AD103 [GeForce RTX 4070 Ti]"))
    assert "amdgpu" in spec.video_cards and "nvidia" in spec.video_cards
    assert spec.nvidia_proprietary is True


# --- assemble → GpuSpec + auto-detect ---------------------------------------

def test_assemble_nvidia_proprietary_implies_a_nvidia_token():
    plan = assemble_plan(
        InstallSelections(disk="sda", root_password="x", nvidia_proprietary=True), _STAGE3)
    assert plan.gpu.nvidia_proprietary is True
    assert "nvidia" in plan.gpu.video_cards


def test_assemble_passes_through_video_cards():
    plan = assemble_plan(
        InstallSelections(disk="sda", root_password="x",
                          video_cards=("amdgpu", "radeonsi")), _STAGE3)
    assert plan.gpu == GpuSpec(video_cards=("amdgpu", "radeonsi"), nvidia_proprietary=False)


def test_assemble_defaults_to_no_gpu():
    plan = assemble_plan(InstallSelections(disk="sda", root_password="x"), _STAGE3)
    assert plan.gpu == GpuSpec()


def test_assemble_kernel_open_gated_on_nvidia_proprietary():
    # kernel-open with the proprietary stack → carried through
    p1 = assemble_plan(InstallSelections(disk="sda", root_password="x",
                                         nvidia_proprietary=True, kernel_open=True), _STAGE3)
    assert p1.gpu.kernel_open is True
    # kernel-open without proprietary NVIDIA is meaningless → dropped
    p2 = assemble_plan(InstallSelections(disk="sda", root_password="x",
                                         video_cards=("amdgpu",), kernel_open=True), _STAGE3)
    assert p2.gpu.kernel_open is False


def test_resolve_gpu_opts_into_proprietary_and_open_for_ada():
    # AD103 = Ada (Turing+) → proprietary stack AND open kernel modules
    spec = resolve_gpu(_lspci(
        "01:00.0 VGA compatible controller: NVIDIA Corporation AD103 [GeForce RTX 4070 Ti]"))
    assert spec == GpuSpec(video_cards=("nvidia",), nvidia_proprietary=True, kernel_open=True)


def test_resolve_gpu_pre_turing_keeps_closed_modules():
    # GP104 = Pascal (pre-Turing) → proprietary, but the closed module (no kernel-open)
    spec = resolve_gpu(_lspci(
        "01:00.0 VGA compatible controller: NVIDIA Corporation GP104 [GeForce GTX 1080]"))
    assert spec.nvidia_proprietary is True and spec.kernel_open is False


def test_resolve_gpu_unknown_codename_defaults_closed():
    # description without a codename → conservative (closed module)
    spec = resolve_gpu(_lspci(
        "01:00.0 VGA compatible controller: NVIDIA Corporation [GeForce RTX 4070 Ti]"))
    assert spec.nvidia_proprietary is True and spec.kernel_open is False


def test_nvidia_open_recommended_by_codename():
    from gest.core.hwflags import detect
    ada = "VGA compatible controller: NVIDIA Corporation AD103 [GeForce RTX 4070 Ti]"
    pascal = "VGA compatible controller: NVIDIA Corporation GP104 [GeForce GTX 1080]"
    assert detect.nvidia_open_recommended(ada) is True
    assert detect.nvidia_open_recommended(pascal) is False


def test_resolve_gpu_amd_is_not_proprietary():
    spec = resolve_gpu(_lspci(
        "07:00.0 VGA compatible controller: Advanced Micro Devices [AMD/ATI] Radeon"))
    assert spec.nvidia_proprietary is False
    assert "amdgpu" in spec.video_cards


# --- VIDEO_CARDS in make.conf -----------------------------------------------

def _make_root(tmp_path, make_conf_body="MAKEOPTS=\"-j1\"\n"):
    root = str(tmp_path / "mnt")
    os.makedirs(os.path.join(root, "etc", "portage"))
    with open(os.path.join(root, "etc", "portage", "make.conf"), "w") as fh:
        fh.write(make_conf_body)
    return root


def test_write_make_conf_sets_video_cards(tmp_path):
    root = _make_root(tmp_path)
    plan = _plan(GpuSpec(video_cards=("nvidia",), nvidia_proprietary=True))
    asyncio.run(WriteMakeConf().run(_ctx(FakeExecutor(), root, plan)))
    body = Path(root, "etc", "portage", "make.conf").read_text()
    assert 'VIDEO_CARDS="nvidia"' in body
    assert 'MAKEOPTS="-j2"' in body


def test_write_make_conf_omits_video_cards_when_no_gpu(tmp_path):
    root = _make_root(tmp_path)
    asyncio.run(WriteMakeConf().run(_ctx(FakeExecutor(), root, _plan())))
    body = Path(root, "etc", "portage", "make.conf").read_text()
    assert "VIDEO_CARDS" not in body


# --- the InstallGpuDrivers step ---------------------------------------------

def _run_gpu_step(tmp_path, spec):
    root = str(tmp_path / "mnt")
    os.makedirs(root)
    fx = FakeExecutor()
    ctx = _ctx(fx, root, _plan(spec))
    step = InstallGpuDrivers()
    assert asyncio.run(step.is_satisfied(ctx)) is False
    asyncio.run(step.run(ctx))
    inner = [c[2:] for c in fx.calls if c[:2] == ["chroot", _ROOT]]
    return root, inner, ctx, step


def test_install_gpu_drivers_nvidia(tmp_path):
    root, inner, ctx, step = _run_gpu_step(
        tmp_path, GpuSpec(video_cards=("nvidia",), nvidia_proprietary=True))
    # license accepted before the emerge
    lic = Path(root + gpu.PACKAGE_LICENSE).read_text()
    assert "x11-drivers/nvidia-drivers NVIDIA-r2" in lic
    # firmware + nvidia-drivers emerged, then modules rebuilt
    assert ["emerge", "--getbinpkg", "--color", "n", "--noreplace",
            "sys-kernel/linux-firmware"] in inner
    assert ["emerge", "--getbinpkg", "--color", "n", "--noreplace",
            "x11-drivers/nvidia-drivers"] in inner
    assert ["emerge", "--color", "n", "@module-rebuild"] in inner
    # modprobe.d modeset/blacklist dropped
    assert "options nvidia_drm modeset=1 fbdev=1" in Path(root + gpu.MODPROBE_CONF).read_text()
    # kernel cmdline hardening written to /etc/default/grub
    grub = Path(root, "etc", "default", "grub").read_text()
    assert "modprobe.blacklist=nouveau" in grub and "nvidia_drm.modeset=1" in grub
    assert asyncio.run(step.is_satisfied(ctx)) is True   # marked done


def test_install_gpu_drivers_firmware_only(tmp_path):
    root, inner, _, _ = _run_gpu_step(tmp_path, GpuSpec())
    lic = Path(root + gpu.PACKAGE_LICENSE).read_text()
    assert "sys-kernel/linux-firmware linux-fw-redistributable" in lic
    assert "NVIDIA-r2" not in lic
    assert ["emerge", "--getbinpkg", "--color", "n", "--noreplace",
            "sys-kernel/linux-firmware"] in inner
    # no nvidia driver, no module rebuild, no modprobe.d
    assert not any("nvidia-drivers" in tok for argv in inner for tok in argv)
    assert ["emerge", "--color", "n", "@module-rebuild"] not in inner
    assert not os.path.exists(root + gpu.MODPROBE_CONF)
    assert not os.path.exists(os.path.join(root, "etc", "default", "grub"))  # no cmdline write
    assert not os.path.exists(root + gpu.PACKAGE_USE)                        # no kernel-open


def test_install_gpu_drivers_kernel_open(tmp_path):
    root, inner, _, _ = _run_gpu_step(
        tmp_path, GpuSpec(video_cards=("nvidia",), nvidia_proprietary=True, kernel_open=True))
    # USE flag set before the emerge; driver still emerged
    assert "x11-drivers/nvidia-drivers kernel-open" in Path(root + gpu.PACKAGE_USE).read_text()
    assert ["emerge", "--getbinpkg", "--color", "n", "--noreplace",
            "x11-drivers/nvidia-drivers"] in inner


def test_install_gpu_drivers_no_package_use_without_kernel_open(tmp_path):
    # default NVIDIA (closed modules) writes no package.use
    root, _, _, _ = _run_gpu_step(
        tmp_path, GpuSpec(video_cards=("nvidia",), nvidia_proprietary=True))
    assert not os.path.exists(root + gpu.PACKAGE_USE)
