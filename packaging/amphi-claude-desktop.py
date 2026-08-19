#!/usr/bin/env python3
"""Sync ``gui-apps/claude-desktop`` into the Amphitheater overlay.

Claude Desktop is Anthropic's official Linux app, shipped as a .deb from their
own apt repo (downloads.claude.ai). This tool reads that repo's live Packages
index for the newest amd64 release, downloads and verifies that .deb against the
index's SHA256, computes its Gentoo Manifest DIST (BLAKE2B + SHA512), and
regenerates Amphitheater's lean ``gui-apps/claude-desktop/`` from the
source-of-truth template in ``packaging/claude-desktop/`` (the version-agnostic
``claude-desktop.ebuild`` + ``metadata.xml`` + a Manifest with just that
release's DIST). Modelled on ``amphi-hede.py``; writes nothing to Amphitheater
without ``--push``.

  packaging/amphi-claude-desktop.py [VERSION] [--push] [--deb PATH]
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
PKG_SRC = REPO_ROOT / "packaging" / "claude-desktop"   # ebuild template + metadata.xml
AMPHI_PUSH = "git@github.com:k5blazerfl/Amphitheater.git"
AMPHI_DRYRUN = "https://github.com/k5blazerfl/Amphitheater.git"
APT_BASE = "https://downloads.claude.ai/claude-desktop/apt/stable"
PACKAGES_URL = f"{APT_BASE}/dists/stable/main/binary-amd64/Packages"
GIT_NAME = "k5blazerfl"
GIT_EMAIL = "k5blazerfl@fastmail.com"


def die(msg: str) -> None:
    sys.exit(f"amphi-claude-desktop: {msg}")


def run(cmd: list[str], cwd: Path | None = None, check: bool = True):
    print("+ " + " ".join(cmd))
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=check)


def has_staged_changes(cwd: Path) -> bool:
    return subprocess.run(["git", "diff", "--cached", "--quiet"],
                          cwd=str(cwd)).returncode != 0


def fetch(url: str, binary: bool = False) -> bytes:
    last: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return resp.read()
        except Exception as exc:  # pragma: no cover - network
            last = exc
            print(f"  fetch attempt {attempt + 1} failed: {exc}; retrying…")
            time.sleep(3)
    die(f"failed to fetch {url}: {last}")
    return b""  # unreachable


def _vkey(ver: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", ver))


def parse_packages(text: str) -> list[dict[str, str]]:
    stanzas = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if line.startswith(" "):  # folded continuation
                continue
            if ":" in line:
                k, _, v = line.partition(":")
                fields[k.strip()] = v.strip()
        if fields.get("Package") == "claude-desktop":
            stanzas.append(fields)
    return stanzas


def pick_release(version: str | None) -> dict[str, str]:
    stanzas = parse_packages(fetch(PACKAGES_URL).decode("utf-8", "replace"))
    if not stanzas:
        die("no claude-desktop entries in the apt Packages index")
    if version:
        for s in stanzas:
            if s.get("Version") == version:
                return s
        die(f"version {version} not found in the apt index")
    return max(stanzas, key=lambda s: _vkey(s.get("Version", "0")))


def load_deb(rel: dict[str, str], deb: str | None) -> bytes:
    if deb:
        data = Path(deb).read_bytes()
    else:
        data = fetch(f"{APT_BASE}/{rel['Filename']}", binary=True)
    # Verify against the index so a corrupt/mismatched download never ships.
    want = rel.get("SHA256", "")
    got = hashlib.sha256(data).hexdigest()
    if want and got != want:
        die(f"SHA256 mismatch: index {want} != download {got}")
    size = rel.get("Size")
    if size and str(len(data)) != size:
        die(f"size mismatch: index {size} != download {len(data)}")
    return data


def dist_line(ver: str, data: bytes) -> str:
    return (f"DIST claude-desktop_{ver}_amd64.deb {len(data)} "
            f"BLAKE2B {hashlib.blake2b(data).hexdigest()} "
            f"SHA512 {hashlib.sha512(data).hexdigest()}")


def write_lean(dest: Path, ver: str, dist: str) -> None:
    """Regenerate Amphitheater's gui-apps/claude-desktop/ from the template: the
    versioned ebuild (older release ebuilds pruned), metadata.xml, and a Manifest
    with just this release's DIST."""
    dest.mkdir(parents=True, exist_ok=True)
    for p in list(dest.glob("claude-desktop-*.ebuild")):
        p.unlink()
    ebuild = (PKG_SRC / "claude-desktop.ebuild").read_text(encoding="utf-8")
    (dest / f"claude-desktop-{ver}.ebuild").write_text(ebuild, encoding="utf-8")
    meta = PKG_SRC / "metadata.xml"
    if meta.exists():
        (dest / "metadata.xml").write_text(meta.read_text(encoding="utf-8"),
                                           encoding="utf-8")
    (dest / "Manifest").write_text(dist + "\n", encoding="utf-8")


def sync(ver: str, dist: str, push: bool) -> int:
    url = AMPHI_PUSH if push else AMPHI_DRYRUN
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "Amphitheater"
        run(["git", "clone", "--depth", "1", url, str(clone)])
        write_lean(clone / "gui-apps" / "claude-desktop", ver, dist)
        run(["git", "config", "user.name", GIT_NAME], cwd=clone)
        run(["git", "config", "user.email", GIT_EMAIL], cwd=clone)
        run(["git", "add", "-A", "gui-apps/claude-desktop"], cwd=clone)
        if not has_staged_changes(clone):
            print(f"amphi-claude-desktop: gui-apps/claude-desktop already at v{ver}")
            return 0
        if not push:
            run(["git", "--no-pager", "diff", "--cached", "--stat"], cwd=clone,
                check=False)
            print(f"amphi-claude-desktop: DRY RUN — would push v{ver} to Amphitheater")
            return 0
        msg = (f"gui-apps/claude-desktop: v{ver} (official Anthropic .deb)\n\n"
               f"Generated by GeST packaging/amphi-claude-desktop.py: the versioned "
               f"ebuild + Manifest DIST for Anthropic's official Linux .deb v{ver}.\n\n"
               f"Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>")
        run(["git", "commit", "-m", msg], cwd=clone)
        run(["git", "push", "origin", "HEAD"], cwd=clone)
        print(f"amphi-claude-desktop: pushed v{ver} to Amphitheater")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync gui-apps/claude-desktop into Amphitheater.")
    ap.add_argument("version", nargs="?", help="version to ship (default: newest in the apt index)")
    ap.add_argument("--push", action="store_true", help="commit and push to Amphitheater")
    ap.add_argument("--deb", help="use a local .deb instead of downloading")
    args = ap.parse_args()

    rel = pick_release(args.version)
    ver = rel["Version"]
    print(f"amphi-claude-desktop: claude-desktop {ver}  (push={args.push})")
    dist = dist_line(ver, load_deb(rel, args.deb))
    print(f"  {dist}")
    return sync(ver, dist, args.push)


if __name__ == "__main__":
    raise SystemExit(main())
