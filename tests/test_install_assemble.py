"""CI-safe tests for the installer's plan assembly: InstallSelections → InstallPlan
is pure, validated, and stage3-resolution parses a mirror index over a fake fetch."""

import pytest

from gest.core.install import assemble
from gest.core.install.assemble import InstallSelections, assemble_plan, resolve_stage3
from gest.core.stage3.model import DEFAULT_VARIANT, Stage3Selection, Stage3Variant

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
    assert plan.kernel.method == "make"
    assert plan.bootloader.firmware == "uefi"
    assert plan.hostname == "gentoo" and plan.timezone == "UTC"
    assert plan.binary_pref is True
    # the root password is NOT in the plan (it stays on the selections as a secret)
    assert not hasattr(plan, "root_password") or isinstance(plan.root_password, bool)


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


# --- resolve_stage3 (I/O, faked) --------------------------------------------

def test_resolve_stage3_parses_the_index(monkeypatch):
    relpath = "20240728T170331Z/stage3-amd64-openrc-20240728T170331Z.tar.xz"
    captured = {}

    def fake_fetch(url):
        captured["url"] = url
        return f"# ts\n{relpath} 268435456\n"

    monkeypatch.setattr(assemble.index, "fetch_text", fake_fetch)
    sel = resolve_stage3(DEFAULT_VARIANT)
    assert "latest-stage3-openrc.txt" in captured["url"]
    assert sel.filename == "stage3-amd64-openrc-20240728T170331Z.tar.xz"
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
    assert "latest-stage3-hardened-openrc.txt" in seen["url"]
