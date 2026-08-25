"""Tests for the license-gate review core (gest.core.install.licensing).

Covers the pure ``review_licenses`` (entails/relevance/blockers/warnings per rung),
the ``license_agreements`` plan convenience, ``Agreement.text_path``, and the
``read_license_text`` [View] reader (present + absent). Hermetic — no tree needed
except a tmp_path for the reader.
"""

import pytest

from gest.core.bootloader.install import InstallConfig
from gest.core.disk import mount as disk_mount
from gest.core.disk import provision
from gest.core.install import licensing
from gest.core.install.licensing import (
    Agreement,
    license_agreements,
    read_license_text,
    review_licenses,
)
from gest.core.install.plan import GpuSpec, InstallPlan
from gest.core.kernel.build import BuildConfig
from gest.core.stage3.model import Stage3Selection

_STAGE3 = Stage3Selection(
    url="https://m/s.tar.xz", filename="s.tar.xz", size=1,
    digests_url="https://m/s.DIGESTS", signature_url="https://m/s.asc")


def _plan(*, license="full", nvidia=False) -> InstallPlan:
    disk = provision.uefi_plan("sda", "512M", "8G", "ext4")
    return InstallPlan(
        disk=disk, mount=disk_mount.derive_mount_plan(disk, "/mnt/gentoo"), stage3=_STAGE3,
        kernel=BuildConfig(method="make", jobs=2), bootloader=InstallConfig(firmware="uefi"),
        hostname="gentoo", timezone="UTC", locale="C.UTF-8", keymap="us",
        license=license, gpu=GpuSpec(video_cards=("nvidia",) if nvidia else (),
                                     nvidia_proprietary=nvidia))


# --- Full ------------------------------------------------------------------

def test_full_with_nvidia_marks_firmware_and_nvidia_required_no_blockers():
    r = review_licenses("full", nvidia=True)
    assert r.ok and not r.blockers and not r.warnings
    assert {a.label for a in r.required} == {"Firmware", "NVIDIA driver"}
    assert r.accept_value == "@BINARY-REDISTRIBUTABLE @EULA"


def test_full_without_nvidia_shows_nvidia_covered_but_not_required():
    r = review_licenses("full", nvidia=False)
    assert r.ok
    labels = {a.label for a in r.entails}
    assert labels == {"Firmware", "NVIDIA driver"}          # both shown (covered)
    assert r.required_labels() == ("Firmware",)             # only firmware exercised
    # NVIDIA driver is present but de-emphasised (not required by this install)
    nv = next(a for a in r.entails if a.label == "NVIDIA driver")
    assert nv.required_by_this_install is False


def test_entails_is_required_first():
    r = review_licenses("full", nvidia=False)
    # firmware (required) sorts before the covered-but-unused NVIDIA driver
    assert [a.label for a in r.entails] == ["Firmware", "NVIDIA driver"]


# --- Redistributable -------------------------------------------------------

def test_redistributable_covers_firmware_and_nvidia():
    r = review_licenses("redistributable", nvidia=True)
    assert r.ok and not r.blockers
    assert {a.label for a in r.required} == {"Firmware", "NVIDIA driver"}
    assert r.accept_value == "@BINARY-REDISTRIBUTABLE"


# --- Libre -----------------------------------------------------------------

def test_libre_with_nvidia_blocks():
    r = review_licenses("libre", nvidia=True)
    assert not r.ok and r.blockers
    assert "NVIDIA" in r.blockers[0]
    assert r.entails == ()                                  # @FREE covers none of them


def test_libre_without_nvidia_warns_but_allows():
    r = review_licenses("libre", nvidia=False)
    assert r.ok                                             # a genuinely-libre install is valid
    assert r.warnings and not r.blockers
    assert "firmware" in r.warnings[0].lower()


# --- EULA relevance --------------------------------------------------------

def test_full_accepts_a_required_eula():
    r = review_licenses("full", nvidia=False, eulas=["google-chrome"])
    assert r.ok
    chrome = next(a for a in r.entails if a.name == "google-chrome")
    assert chrome.required_by_this_install and chrome.group == licensing.EULA


def test_redistributable_blocks_on_a_required_eula():
    r = review_licenses("redistributable", nvidia=False, eulas=["google-chrome"])
    assert not r.ok
    assert "EULA" in r.blockers[0] and "google-chrome" in r.blockers[0]


def test_libre_with_eula_warns_on_firmware_and_blocks_on_eula():
    r = review_licenses("libre", nvidia=False, eulas=["Steam"])
    assert r.warnings and r.blockers                        # both surface
    assert not r.ok


# --- misc ------------------------------------------------------------------

def test_unknown_rung_raises():
    with pytest.raises(ValueError):
        review_licenses("bogus")


def test_agreement_text_path():
    a = Agreement("NVIDIA-r2", "NVIDIA driver", licensing.BINARY_REDISTRIBUTABLE, "x")
    assert a.text_path == "/var/db/repos/gentoo/licenses/NVIDIA-r2"


def test_license_agreements_reads_rung_and_nvidia_off_the_plan():
    assert review_licenses("full", nvidia=True).required_labels() == \
        license_agreements(_plan(license="full", nvidia=True)).required_labels()
    r = license_agreements(_plan(license="libre", nvidia=True))
    assert not r.ok                                         # libre + NVIDIA plan → blocked


def test_read_license_text_present_and_absent(tmp_path):
    (tmp_path / "NVIDIA-r2").write_text("the NVIDIA license text\n", encoding="utf-8")
    assert "NVIDIA license" in read_license_text("NVIDIA-r2", licenses_dir=str(tmp_path))
    assert read_license_text("does-not-exist", licenses_dir=str(tmp_path)) == ""
