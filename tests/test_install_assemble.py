"""CI-safe tests for the installer's plan assembly: InstallSelections → InstallPlan
is pure, validated, and stage3-resolution parses a mirror index over a fake fetch."""

import pytest

from gest.core.bootloader.install import install_steps
from gest.core.install import assemble
from gest.core.install.assemble import InstallSelections, assemble_plan, resolve_stage3
from gest.core.install.plan import NetworkSpec, UserSpec
from gest.core.stage3.model import (
    ARM64_VARIANTS,
    DEFAULT_VARIANT,
    Stage3Selection,
    Stage3Variant,
)

_S3 = Stage3Selection(
    url="https://m/stage3.tar.xz", filename="stage3.tar.xz", size=9,
    digests_url="https://m/stage3.tar.xz.DIGESTS", signature_url="https://m/stage3.tar.xz.asc")


def _ok_selection(**kw) -> InstallSelections:
    base = dict(disk="sda", root_password="hunter2")
    base.update(kw)
    return InstallSelections(**base)


# --- assemble_plan (pure) ---------------------------------------------------

def test_assemble_builds_a_full_plan():
    plan = assemble_plan(_ok_selection(swap_size="4G", root_fs="xfs"), _S3)
    assert plan.disk.disk == "/dev/sda"
    assert plan.mount.root == "/mnt/gentoo"
    assert plan.stage3 is _S3
    assert plan.kernel.method == "genkernel"                    # auto-config source build
    assert plan.profile == "default/linux/amd64/23.0/systemd"   # systemd default
    assert plan.bootloader.firmware == "uefi"
    assert plan.hostname == "gentoo" and plan.timezone == "UTC"
    assert plan.binary_pref is True
    # the root password is NOT in the plan (it stays on the selections as a secret)
    assert not hasattr(plan, "root_password") or isinstance(plan.root_password, bool)


def test_assemble_carries_tier2_selection():
    assert assemble_plan(_ok_selection(), _S3).tier2 == frozenset()
    plan = assemble_plan(_ok_selection(tier2={"sshd", "sysctl"}), _S3)
    assert plan.tier2 == frozenset({"sshd", "sysctl"})


def test_assemble_defaults_to_a_seamless_hede_desktop():
    # GeSI's default: install the HeDE desktop, and (since that plants plymouth +
    # the theme) seamless boot takes effect — both halves of the look on.
    plan = assemble_plan(_ok_selection(), _S3)
    assert plan.desktop is True
    assert plan.kernel.plymouth is True
    assert plan.bootloader.seamless is True


def test_assemble_base_gentoo_gates_seamless_off():
    # A base-Gentoo install (no desktop) can't seamless-boot — plymouth/theme aren't
    # there — so seamless is forced off even if requested, rather than a broken install.
    plan = assemble_plan(_ok_selection(install_desktop=False, seamless=True), _S3)
    assert plan.desktop is False
    assert plan.kernel.plymouth is False
    assert plan.bootloader.seamless is False


def test_assemble_desktop_with_seamless_off_is_a_plain_boot():
    plan = assemble_plan(_ok_selection(seamless=False), _S3)
    assert plan.desktop is True
    assert plan.kernel.plymouth is False
    assert plan.bootloader.seamless is False


def test_assemble_seamless_genkernel_bakes_plymouth_into_initramfs():
    from gest.core.kernel.build import build_steps
    plan = assemble_plan(_ok_selection(kernel_method="genkernel"), _S3)
    argv = build_steps(plan.kernel)[0].argv
    assert "--plymouth" in argv and "--plymouth-theme=hede" in argv


def test_profile_name_is_systemd_for_systemd_flavors():
    from gest.core.install.assemble import profile_name
    assert profile_name("amd64", "systemd") == "default/linux/amd64/23.0/systemd"
    assert profile_name("amd64", "desktop-systemd") == "default/linux/amd64/23.0/systemd"
    assert profile_name("amd64", "openrc") == "default/linux/amd64/23.0"
    assert profile_name("arm64", "systemd") == "default/linux/arm64/23.0/systemd"


def test_assemble_profile_follows_the_stage3_flavor():
    from gest.core.stage3.model import VARIANTS
    openrc = next(v for v in VARIANTS if v.flavor == "openrc")
    assert assemble_plan(_ok_selection(variant=openrc), _S3).profile == "default/linux/amd64/23.0"


# --- target arch (Apple Silicon / Asahi groundwork) -------------------------

def test_assemble_defaults_to_amd64_arch():
    assert assemble_plan(_ok_selection(), _S3).arch == "amd64"


def test_assemble_arm64_variant_sets_arch_and_uefi_target():
    # picking an arm64 stage3 variant makes the whole plan arm64; the bootloader
    # step then emits an arm64-efi grub-install (firmware defaults to uefi).
    plan = assemble_plan(_ok_selection(variant=ARM64_VARIANTS[0]), _S3)
    assert plan.arch == "arm64"
    assert "--target=arm64-efi" in install_steps(plan.bootloader, arch=plan.arch)[0].argv


def test_assemble_arm64_rejects_bios():
    with pytest.raises(ValueError):
        assemble_plan(
            _ok_selection(variant=ARM64_VARIANTS[0], firmware="bios", boot_disk="sda"), _S3)


def test_assemble_rejects_unsupported_arch():
    bad = Stage3Variant("riscv", "openrc", "RISC-V")
    with pytest.raises(ValueError):
        assemble_plan(_ok_selection(variant=bad), _S3)


def test_assemble_carries_kernel_and_bootloader_choices():
    sel = _ok_selection(kernel_method="genkernel", kernel_jobs=4, kernel_initramfs=False,
                        firmware="bios", boot_disk="sda")
    plan = assemble_plan(sel, _S3)
    assert (plan.kernel.method, plan.kernel.jobs, plan.kernel.initramfs) == ("genkernel", 4, False)
    assert plan.bootloader.firmware == "bios" and plan.bootloader.disk == "sda"


def test_assemble_rejects_missing_disk_password_and_bad_firmware():
    with pytest.raises(ValueError, match="disk"):
        assemble_plan(InstallSelections(root_password="pw"), _S3)
    with pytest.raises(ValueError, match="password"):
        assemble_plan(InstallSelections(disk="sda"), _S3)
    with pytest.raises(ValueError, match="firmware"):
        assemble_plan(_ok_selection(firmware="coreboot"), _S3)


def test_assemble_rejects_bad_filesystem():
    with pytest.raises(ValueError):
        assemble_plan(_ok_selection(root_fs="zfs"), _S3)   # unsupported fs → uefi_plan raises


def test_default_selections_need_a_disk_and_password():
    # a fresh overview is not yet installable
    with pytest.raises(ValueError):
        assemble_plan(InstallSelections(), _S3)


# --- user account -----------------------------------------------------------

def test_assemble_builds_a_user_when_requested():
    sel = _ok_selection(create_user=True, user_name="tux", user_comment="Tux",
                        user_shell="/bin/zsh", user_wheel=True)
    plan = assemble_plan(sel, _S3)
    assert isinstance(plan.user, UserSpec)
    assert plan.user == UserSpec(name="tux", comment="Tux", shell="/bin/zsh", wheel=True)


def test_assemble_omits_the_user_by_default():
    assert assemble_plan(_ok_selection(), _S3).user is None
    # create_user False even with a name filled in → no user
    assert assemble_plan(_ok_selection(user_name="tux"), _S3).user is None


def test_assemble_rejects_a_bad_or_empty_user_name():
    with pytest.raises(ValueError, match="user name"):
        assemble_plan(_ok_selection(create_user=True, user_name=""), _S3)
    with pytest.raises(ValueError, match="user name"):
        assemble_plan(_ok_selection(create_user=True, user_name="1bad"), _S3)


# --- target network ---------------------------------------------------------

def test_assemble_defaults_the_network_when_interface_blank():
    plan = assemble_plan(_ok_selection(), _S3)
    assert plan.network == NetworkSpec()   # default, no raise


def test_assemble_carries_a_static_network():
    sel = _ok_selection(net_interface="eth0", net_dhcp=False,
                        net_address="192.168.1.5/24", net_gateway="192.168.1.1",
                        net_nameservers=("1.1.1.1", "9.9.9.9"))
    plan = assemble_plan(sel, _S3)
    assert plan.network == NetworkSpec(
        dhcp=False, interface="eth0", address="192.168.1.5/24",
        gateway="192.168.1.1", nameservers=("1.1.1.1", "9.9.9.9"))


def test_assemble_carries_a_dhcp_network():
    plan = assemble_plan(_ok_selection(net_interface="eth0"), _S3)
    assert plan.network.dhcp is True and plan.network.interface == "eth0"


def test_assemble_rejects_a_bad_static_network():
    with pytest.raises(ValueError, match="address"):
        assemble_plan(_ok_selection(net_interface="eth0", net_dhcp=False,
                                    net_address="192.168.1.5"), _S3)   # no CIDR
    with pytest.raises(ValueError, match="gateway"):
        assemble_plan(_ok_selection(net_interface="eth0", net_dhcp=False,
                                    net_address="192.168.1.5/24",
                                    net_gateway="not-an-ip"), _S3)
    with pytest.raises(ValueError, match="nameserver"):
        assemble_plan(_ok_selection(net_interface="eth0", net_dhcp=False,
                                    net_address="192.168.1.5/24",
                                    net_nameservers=("1.1.1.1", "nope")), _S3)


# --- system fields validated ------------------------------------------------

def test_assemble_carries_system_fields():
    sel = _ok_selection(hostname="workstation", timezone="America/New_York",
                        locale="en_US.UTF-8", keymap="de-latin1")
    plan = assemble_plan(sel, _S3)
    assert plan.hostname == "workstation"
    assert plan.timezone == "America/New_York"
    assert plan.locale == "en_US.UTF-8"
    assert plan.keymap == "de-latin1"


def test_assemble_rejects_bad_system_fields():
    with pytest.raises(ValueError, match="hostname"):
        assemble_plan(_ok_selection(hostname="bad_host!"), _S3)
    with pytest.raises(ValueError, match="timezone"):
        assemble_plan(_ok_selection(timezone="../etc/passwd"), _S3)
    with pytest.raises(ValueError, match="locale"):
        assemble_plan(_ok_selection(locale="en US"), _S3)
    with pytest.raises(ValueError, match="keymap"):
        assemble_plan(_ok_selection(keymap="bad key"), _S3)


# --- resolve_stage3 (I/O, faked) --------------------------------------------

def test_resolve_stage3_parses_the_index(monkeypatch):
    # DEFAULT_VARIANT is now Standard (systemd) — the base a HeDE install needs.
    relpath = "20240728T170331Z/stage3-amd64-systemd-20240728T170331Z.tar.xz"
    captured = {}

    def fake_fetch(url):
        captured["url"] = url
        return f"# ts\n{relpath} 268435456\n"

    monkeypatch.setattr(assemble.index, "fetch_text", fake_fetch)
    sel = resolve_stage3(DEFAULT_VARIANT)
    assert "latest-stage3-amd64-systemd.txt" in captured["url"]
    assert sel.filename == "stage3-amd64-systemd-20240728T170331Z.tar.xz"
    assert sel.size == 268435456
    assert sel.url.endswith(relpath)
    assert sel.digests_url == sel.url + ".DIGESTS"
    assert sel.signature_url == sel.url + ".asc"


def test_resolve_stage3_uses_the_variant_flavor(monkeypatch):
    seen = {}

    def fake_fetch(url):
        seen["url"] = url
        return "x/stage3.tar.xz 1\n"

    monkeypatch.setattr(assemble.index, "fetch_text", fake_fetch)
    resolve_stage3(Stage3Variant("amd64", "hardened-openrc", "Hardened"))
    assert "latest-stage3-amd64-hardened-openrc.txt" in seen["url"]
