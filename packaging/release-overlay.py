#!/usr/bin/env python3
"""Generate and sync the GeST Gentoo overlays for a release — from one source.

**Single source of truth:** ``packaging/overlay/app-admin/gest/`` in THIS repo,
which keeps the full version history with a complete Manifest. Everything else is
*derived* from it and from the GitHub tag tarball, so a release can never ship an
ebuild without its Manifest DIST digest — the recurring drift bug that makes
``emerge`` fail with "Insufficient data for checksum verification".

For a version X.Y.Z this script:

1. Downloads the ``vX.Y.Z`` tag tarball from GitHub and computes its DIST line
   (byte size + BLAKE2b-512 + SHA512 — byte-identical to ``pkgdev manifest``).
2. **Authoritative overlay** (this repo): ensures ``gest-X.Y.Z.ebuild`` exists
   (copied from the newest existing versioned ebuild — ebuilds are
   version-independent, only ``$PV`` changes) and upserts the DIST line into the
   Manifest, kept as full sorted history.
3. **Amphitheater overlay** (lean / latest-only): regenerates ``app-admin/gest/``
   to hold just ``gest-X.Y.Z.ebuild`` + ``gest-9999.ebuild`` + ``metadata.xml``
   and a Manifest with only the X.Y.Z DIST line (older release ebuilds pruned).

By default it only writes files and reports. Pass ``--push`` to commit + push:
the authoritative change to this repo (``origin``) and the Amphitheater change via
an ephemeral clone. Scope with ``--gest-only`` / ``--amphitheater-only``.

  packaging/release-overlay.py [VERSION] [--push] [--gest-only|--amphitheater-only]
                               [--tarball PATH]

VERSION defaults to pyproject.toml's version (a leading ``v`` is accepted).
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
GEST_DIR = REPO_ROOT / "packaging" / "overlay" / "app-admin" / "gest"
AMPHI_URL = "git@github.com:k5blazerfl/Amphitheater.git"
TARBALL_URL = "https://github.com/k5blazerfl/GeST/archive/refs/tags/v{ver}.tar.gz"
GIT_NAME = "k5blazerfl"
GIT_EMAIL = "k5blazerfl@fastmail.com"

_EBUILD_RE = re.compile(r"^gest-(\d+\.\d+\.\d+)\.ebuild$")
_DIST_RE = re.compile(
    r"^DIST gest-(?P<ver>\d+\.\d+\.\d+)\.tar\.gz (?P<size>\d+) "
    r"BLAKE2B (?P<b2>[0-9a-f]{128}) SHA512 (?P<s5>[0-9a-f]{128})$")


def vkey(ver: str) -> tuple[int, ...]:
    return tuple(int(x) for x in ver.split("."))


def die(msg: str) -> None:
    sys.exit(f"release-overlay: {msg}")


def run(cmd: list[str], cwd: Path | None = None, check: bool = True):
    print("+ " + " ".join(cmd))
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=check)


def has_staged_changes(cwd: Path) -> bool:
    return subprocess.run(["git", "diff", "--cached", "--quiet"],
                          cwd=str(cwd)).returncode != 0


# -- version + tarball -------------------------------------------------------

def read_pyproject_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"', text, re.M)
    if not m:
        die("could not find version in pyproject.toml")
    return m.group(1)


def norm_version(v: str) -> str:
    return v[1:] if v.startswith("v") else v


def load_tarball(ver: str, tarball: str | None) -> bytes:
    if tarball:
        return Path(tarball).read_bytes()
    url = TARBALL_URL.format(ver=ver)
    last: Exception | None = None
    for attempt in range(5):
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
    return (f"DIST gest-{ver}.tar.gz {len(data)} "
            f"BLAKE2B {hashlib.blake2b(data).hexdigest()} "
            f"SHA512 {hashlib.sha512(data).hexdigest()}")


# -- Manifest + ebuild helpers ----------------------------------------------

def parse_manifest(path: Path) -> dict[str, str]:
    dists: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _DIST_RE.match(line.strip())
            if m:
                dists[m.group("ver")] = line.strip()
    return dists


def render_manifest(dists: dict[str, str]) -> str:
    lines = [dists[v] for v in sorted(dists, key=vkey)]
    return "\n".join(lines) + "\n" if lines else ""


def release_versions(gest_dir: Path) -> list[str]:
    vers = [m.group(1) for p in gest_dir.glob("gest-*.ebuild")
            if (m := _EBUILD_RE.match(p.name))]
    if not vers:
        die(f"no versioned ebuilds in {gest_dir}")
    return sorted(vers, key=vkey)


def newest_ebuild_text(gest_dir: Path) -> str:
    newest = release_versions(gest_dir)[-1]
    return (gest_dir / f"gest-{newest}.ebuild").read_text(encoding="utf-8")


def consistency_problems(gest_dir: Path) -> list[str]:
    dists = parse_manifest(gest_dir / "Manifest")
    return [f"{p.name} has no Manifest DIST entry"
            for p in sorted(gest_dir.glob("gest-*.ebuild"))
            if (m := _EBUILD_RE.match(p.name)) and m.group(1) not in dists]


# -- overlay writers ---------------------------------------------------------

def update_authoritative(ver: str, dist: str) -> None:
    """Ensure this repo's overlay has gest-<ver>.ebuild and its DIST line."""
    target = GEST_DIR / f"gest-{ver}.ebuild"
    if not target.exists():
        target.write_text(newest_ebuild_text(GEST_DIR), encoding="utf-8")
        print(f"  wrote {target.relative_to(REPO_ROOT)} (copied from newest ebuild)")
    manifest = GEST_DIR / "Manifest"
    dists = parse_manifest(manifest)
    dists[ver] = dist
    manifest.write_text(render_manifest(dists), encoding="utf-8")
    print(f"  upserted DIST for {ver} into {manifest.relative_to(REPO_ROOT)}")


def write_lean(dest_gest: Path, ver: str, dist: str, template: Path) -> None:
    """Render Amphitheater's lean app-admin/gest/ from the authoritative overlay.

    The authoritative overlay is the single source of truth, so everything here
    is *derived* from it: the latest release ebuild (older release ebuilds are
    pruned), a Manifest with only that release's DIST line, and the shared
    ``gest-9999`` + ``metadata.xml`` copied over verbatim.
    """
    dest_gest.mkdir(parents=True, exist_ok=True)
    for p in list(dest_gest.glob("gest-*.ebuild")):
        if _EBUILD_RE.match(p.name):
            p.unlink()  # drop stale release ebuilds; keep gest-9999
    (dest_gest / f"gest-{ver}.ebuild").write_text(
        newest_ebuild_text(template), encoding="utf-8")
    for extra in ("gest-9999.ebuild", "metadata.xml"):
        src = template / extra
        if src.exists():
            (dest_gest / extra).write_text(src.read_text(encoding="utf-8"),
                                           encoding="utf-8")
    (dest_gest / "Manifest").write_text(dist + "\n", encoding="utf-8")


# -- push flows --------------------------------------------------------------

def commit_authoritative(ver: str, push: bool) -> None:
    files = [str(GEST_DIR / f"gest-{ver}.ebuild"), str(GEST_DIR / "Manifest")]
    run(["git", "add", *files], cwd=REPO_ROOT)
    if not has_staged_changes(REPO_ROOT):
        print("  authoritative overlay already up to date")
        return
    if not push:
        print("  (no --push) authoritative overlay files written + staged; "
              "commit them yourself, or re-run with --push")
        return
    msg = (f"packaging: versioned ebuild + Manifest for the v{ver} release\n\n"
           f"Generated by packaging/release-overlay.py: adds gest-{ver}.ebuild "
           f"and the Manifest DIST entry for the v{ver} tag tarball.\n\n"
           f"Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>")
    run(["git", "commit", "-m", msg], cwd=REPO_ROOT)
    run(["git", "push", "origin", "HEAD"], cwd=REPO_ROOT)


def sync_amphitheater(ver: str, dist: str, push: bool) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "Amphitheater"
        run(["git", "clone", "--depth", "1", AMPHI_URL, str(clone)])
        write_lean(clone / "app-admin" / "gest", ver, dist, GEST_DIR)
        run(["git", "config", "user.name", GIT_NAME], cwd=clone)
        run(["git", "config", "user.email", GIT_EMAIL], cwd=clone)
        run(["git", "add", "-A", "app-admin/gest"], cwd=clone)
        if not has_staged_changes(clone):
            print("  Amphitheater already lean at this version")
            return
        if not push:
            run(["git", "--no-pager", "diff", "--cached", "--stat"], cwd=clone)
            print("  (no --push) Amphitheater changes prepared but not pushed")
            return
        msg = (f"app-admin/gest: v{ver} (lean overlay sync)\n\n"
               f"Generated by GeST packaging/release-overlay.py: the lean "
               f"latest-only mirror of the authoritative GeST overlay.\n\n"
               f"Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>")
        run(["git", "commit", "-m", msg], cwd=clone)
        run(["git", "push", "origin", "HEAD"], cwd=clone)


# -- main --------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Generate + sync the GeST overlays.")
    ap.add_argument("version", nargs="?", help="release version (default: pyproject)")
    ap.add_argument("--push", action="store_true", help="commit and push changes")
    ap.add_argument("--tarball", help="use a local tarball instead of downloading")
    scope = ap.add_mutually_exclusive_group()
    scope.add_argument("--gest-only", action="store_true",
                       help="only update this repo's authoritative overlay")
    scope.add_argument("--amphitheater-only", action="store_true",
                       help="only regenerate + sync the Amphitheater overlay")
    args = ap.parse_args()

    ver = norm_version(args.version or read_pyproject_version())
    if not re.fullmatch(r"\d+\.\d+\.\d+", ver):
        die(f"not a X.Y.Z version: {ver!r}")
    print(f"release-overlay: gest {ver}  (push={args.push})")

    data = load_tarball(ver, args.tarball)
    dist = dist_line(ver, data)
    print(f"  {dist}")

    if not args.amphitheater_only:
        update_authoritative(ver, dist)
        problems = consistency_problems(GEST_DIR)
        if problems:
            die("refusing to proceed — " + "; ".join(problems))
        commit_authoritative(ver, args.push)

    if not args.gest_only:
        sync_amphitheater(ver, dist, args.push)

    print("release-overlay: done"
          + ("" if args.push else "  (dry run — nothing pushed; add --push)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
