"""Tests for packaging/livecd/assert-iso-versions.sh — the post-build ISO gate.

Drives the shell script via subprocess with synthetic catalyst logs and a fake
overlay, covering the failure modes it exists to catch: a binary-package
fallback for an image-mutating package, a version that doesn't match the
overlay, and a package that never built. Needs bash (present on CI runners).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parent.parent
          / "packaging" / "livecd" / "assert-iso-versions.sh")

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _overlay(root: Path, gest="0.53.2", hede="0.3.5") -> Path:
    (root / "app-admin" / "gest").mkdir(parents=True)
    (root / "app-admin" / "gest" / f"gest-{gest}.ebuild").touch()
    if hede is not None:
        (root / "gui-apps" / "hede").mkdir(parents=True)
        (root / "gui-apps" / "hede" / f"hede-{hede}.ebuild").touch()
    return root


def _run(log: Path, overlay: Path, with_hede=True):
    env = {"GEST_OVERLAY": str(overlay), "PATH": "/usr/bin:/bin"}
    if with_hede:
        env["HEDE_OVERLAY"] = str(overlay)
    return subprocess.run(["bash", str(SCRIPT), str(log)],
                          env=env, capture_output=True, text=True)


def _log(tmp_path: Path, *lines: str) -> Path:
    p = tmp_path / "build.log"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_source_built_matching_versions_pass(tmp_path):
    ov = _overlay(tmp_path / "ov")
    log = _log(tmp_path,
               ">>> Emerging (12 of 40) app-admin/gest-0.53.2::gest",
               ">>> Emerging (20 of 40) gui-apps/hede-0.3.5::amphitheater")
    r = _run(log, ov)
    assert r.returncode == 0, r.stderr


def test_binary_package_for_hede_fails(tmp_path):
    ov = _overlay(tmp_path / "ov")
    log = _log(tmp_path,
               ">>> Emerging (12 of 40) app-admin/gest-0.53.2::gest",
               ">>> Emerging binary (20 of 40) gui-apps/hede-0.3.0::amphitheater")
    r = _run(log, ov)
    assert r.returncode == 1
    assert "BINARY" in r.stderr


def test_version_mismatch_fails(tmp_path):
    ov = _overlay(tmp_path / "ov")            # overlay offers 0.53.2
    log = _log(tmp_path,
               ">>> Emerging (12 of 40) app-admin/gest-0.53.1::gest",  # image built 0.53.1
               ">>> Emerging (20 of 40) gui-apps/hede-0.3.5::amphitheater")
    r = _run(log, ov)
    assert r.returncode == 1
    assert "overlay offers 0.53.2" in r.stderr


def test_gest_never_emerged_fails(tmp_path):
    ov = _overlay(tmp_path / "ov")
    log = _log(tmp_path,
               ">>> Emerging (20 of 40) gui-apps/hede-0.3.5::amphitheater")
    r = _run(log, ov)
    assert r.returncode == 1
    assert "never emerged" in r.stderr


def test_hede_skipped_when_no_hede_overlay(tmp_path):
    # arm64 / non-amd64: no HEDE_OVERLAY exported → only gest is checked.
    ov = _overlay(tmp_path / "ov")
    log = _log(tmp_path, ">>> Emerging (12 of 40) app-admin/gest-0.53.2::gest")
    r = _run(log, ov, with_hede=False)
    assert r.returncode == 0, r.stderr
