"""CI guard: every overlay ebuild must carry its Manifest DIST digest.

This is the structural fix for the recurring drift bug — a ``gest-X.Y.Z.ebuild``
shipped without a matching ``DIST gest-X.Y.Z.tar.gz`` line makes ``emerge`` fail
with "Insufficient data for checksum verification". The release tooling
(``packaging/release-overlay.py``) writes both together; this test is the
backstop that fails CI if a hand-edit ever splits them again.

Pure stdlib so it runs in the dependency-light CI subset (see .github/workflows).
"""

import re
from pathlib import Path

GEST_DIR = (Path(__file__).resolve().parent.parent
            / "packaging" / "overlay" / "app-admin" / "gest")

_EBUILD_RE = re.compile(r"^gest-(\d+\.\d+\.\d+)\.ebuild$")
_DIST_RE = re.compile(
    r"^DIST gest-(\d+\.\d+\.\d+)\.tar\.gz \d+ "
    r"BLAKE2B [0-9a-f]{128} SHA512 [0-9a-f]{128}$")


def _manifest_versions() -> set[str]:
    versions: set[str] = set()
    for line in (GEST_DIR / "Manifest").read_text(encoding="utf-8").splitlines():
        m = _DIST_RE.match(line.strip())
        if m:
            versions.add(m.group(1))
    return versions


def _ebuild_versions() -> set[str]:
    return {m.group(1) for p in GEST_DIR.glob("gest-*.ebuild")
            if (m := _EBUILD_RE.match(p.name))}


def test_every_release_ebuild_has_a_manifest_dist():
    missing = sorted(_ebuild_versions() - _manifest_versions())
    assert not missing, f"ebuilds shipped without a Manifest DIST entry: {missing}"


def test_manifest_lines_are_well_formed():
    lines = (GEST_DIR / "Manifest").read_text(encoding="utf-8").splitlines()
    malformed = [ln for ln in lines if ln.strip() and not _DIST_RE.match(ln.strip())]
    assert not malformed, f"malformed Manifest lines: {malformed}"


def test_live_ebuild_is_present_and_unmanifested():
    # gest-9999 tracks git (no distfile), so it must NOT appear in the Manifest.
    assert (GEST_DIR / "gest-9999.ebuild").exists()
    assert "9999" not in _manifest_versions()
