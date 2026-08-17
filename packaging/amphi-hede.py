#!/usr/bin/env python3
"""Sync the versioned ``gui-apps/hede`` ebuild into the Amphitheater overlay.

Companion to ``mirror-hede.py``: once ``hede/`` is mirrored to ``k5blazerfl/HeDE``
and tagged ``vX.Y.Z``, this downloads that HeDE tag tarball, computes its Manifest
DIST, and regenerates Amphitheater's lean ``gui-apps/hede/`` — the amd64 desktop
the live-CD installs (``hede-X.Y.Z.ebuild`` + ``hede-9999.ebuild`` + ``metadata.xml``
+ a Manifest with only the X.Y.Z DIST). The ebuild is version-independent
(``hede-9999.ebuild`` handles both PV cases via SRC_URI), so the release ebuild is
a copy of it.

HeDE keeps its own version line — the version comes from ``hede/CMakeLists.txt``
(``project(hede VERSION X.Y.Z)``), NOT the gest release version. Modelled on
``release-overlay.py``; writes nothing to Amphitheater without ``--push``.

  packaging/amphi-hede.py [VERSION] [--push] [--tarball PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HEDE_PKG = REPO_ROOT / "hede" / "packaging"          # hede-9999.ebuild + metadata.xml
AMPHI_PUSH = "git@github.com:k5blazerfl/Amphitheater.git"
AMPHI_DRYRUN = "https://github.com/k5blazerfl/Amphitheater.git"
HEDE_TARBALL_URL = "https://github.com/k5blazerfl/HeDE/archive/refs/tags/v{ver}.tar.gz"
GIT_NAME = "k5blazerfl"
GIT_EMAIL = "k5blazerfl@fastmail.com"
_REL_EBUILD = re.compile(r"^hede-\d+\.\d+\.\d+\.ebuild$")


def die(msg: str) -> None:
    sys.exit(f"amphi-hede: {msg}")


def run(cmd: list[str], cwd: Path | None = None, check: bool = True):
    print("+ " + " ".join(cmd))
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=check)


def has_staged_changes(cwd: Path) -> bool:
    return subprocess.run(["git", "diff", "--cached", "--quiet"],
                          cwd=str(cwd)).returncode != 0


def hede_version() -> str:
    text = (REPO_ROOT / "hede" / "CMakeLists.txt").read_text(encoding="utf-8")
    m = re.search(r"project\(hede\s+VERSION\s+(\d+\.\d+\.\d+)", text)
    if not m:
        die("could not read HeDE version from hede/CMakeLists.txt")
    return m.group(1)  # type: ignore[union-attr]


def norm_version(v: str) -> str:
    v = v.lstrip("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", v):
        die(f"expected X.Y.Z, got {v!r}")
    return v


def load_tarball(ver: str, tarball: str | None) -> bytes:
    if tarball:
        return Path(tarball).read_bytes()
    url = HEDE_TARBALL_URL.format(ver=ver)
    last: Exception | None = None
    for attempt in range(5):  # a freshly-pushed tag's archive takes a moment
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return resp.read()
        except Exception as exc:  # pragma: no cover - network
            last = exc
            print(f"  download attempt {attempt + 1} failed: {exc}; retrying…")
            time.sleep(3)
    die(f"failed to download {url}: {last}")
    return b""  # unreachable


def dist_line(ver: str, data: bytes) -> str:
    return (f"DIST hede-{ver}.tar.gz {len(data)} "
            f"BLAKE2B {hashlib.blake2b(data).hexdigest()} "
            f"SHA512 {hashlib.sha512(data).hexdigest()}")


def write_lean(dest: Path, ver: str, dist: str) -> None:
    """Regenerate Amphitheater's gui-apps/hede/ from hede/packaging/ (source of
    truth): the release ebuild (older release ebuilds pruned), the shared
    hede-9999 + metadata.xml, and a Manifest with just this release's DIST."""
    dest.mkdir(parents=True, exist_ok=True)
    for p in list(dest.glob("hede-*.ebuild")):
        if _REL_EBUILD.match(p.name):
            p.unlink()  # drop stale release ebuilds; keep hede-9999
    ebuild = (HEDE_PKG / "hede-9999.ebuild").read_text(encoding="utf-8")
    (dest / f"hede-{ver}.ebuild").write_text(ebuild, encoding="utf-8")
    (dest / "hede-9999.ebuild").write_text(ebuild, encoding="utf-8")
    meta = HEDE_PKG / "metadata.xml"
    if meta.exists():
        (dest / "metadata.xml").write_text(meta.read_text(encoding="utf-8"),
                                           encoding="utf-8")
    (dest / "Manifest").write_text(dist + "\n", encoding="utf-8")


def sync(ver: str, dist: str, push: bool) -> int:
    url = AMPHI_PUSH if push else AMPHI_DRYRUN
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "Amphitheater"
        run(["git", "clone", "--depth", "1", url, str(clone)])
        write_lean(clone / "gui-apps" / "hede", ver, dist)
        run(["git", "config", "user.name", GIT_NAME], cwd=clone)
        run(["git", "config", "user.email", GIT_EMAIL], cwd=clone)
        run(["git", "add", "-A", "gui-apps/hede"], cwd=clone)
        if not has_staged_changes(clone):
            print(f"amphi-hede: gui-apps/hede already at v{ver}")
            return 0
        if not push:
            run(["git", "--no-pager", "diff", "--cached", "--stat"], cwd=clone,
                check=False)
            print(f"amphi-hede: DRY RUN — would push gui-apps/hede v{ver} to Amphitheater")
            return 0
        msg = (f"gui-apps/hede: v{ver} (lean overlay sync)\n\n"
               f"Generated by GeST packaging/amphi-hede.py: the versioned HeDE "
               f"ebuild + Manifest DIST for the HeDE v{ver} tag tarball.\n\n"
               f"Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>")
        run(["git", "commit", "-m", msg], cwd=clone)
        run(["git", "push", "origin", "HEAD"], cwd=clone)
        print(f"amphi-hede: pushed gui-apps/hede v{ver} to Amphitheater")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync gui-apps/hede into Amphitheater.")
    ap.add_argument("version", nargs="?", help="HeDE version (default: hede/CMakeLists.txt)")
    ap.add_argument("--push", action="store_true", help="commit and push to Amphitheater")
    ap.add_argument("--tarball", help="use a local HeDE tarball instead of downloading")
    args = ap.parse_args()

    ver = norm_version(args.version or hede_version())
    print(f"amphi-hede: hede {ver}  (push={args.push})")
    dist = dist_line(ver, load_tarball(ver, args.tarball))
    print(f"  {dist}")
    return sync(ver, dist, args.push)


if __name__ == "__main__":
    raise SystemExit(main())
