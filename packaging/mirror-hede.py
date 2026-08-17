#!/usr/bin/env python3
"""Mirror the ``hede/`` subtree of THIS repo to the standalone HeDE repo.

HeDE is developed here (``GeST/hede/``) but its ebuild builds from a separate
repo (``k5blazerfl/HeDE``, the ``EGIT_REPO_URI`` / tag-tarball source). Nothing
carried ``hede/`` across, so a ``hede/``-only change landed in GeST but never
shipped — the manual step this script removes.

On a release it makes the HeDE repo a byte-for-byte mirror of ``hede/`` at the
tagged commit and tags it ``vX.Y.Z``, so:
  * the live ``hede-9999`` ebuild (git-r3 on HeDE ``main``) tracks GeST, and
  * the versioned ebuild's ``SRC_URI`` (``HeDE/archive/.../vX.Y.Z.tar.gz``)
    resolves — which the Amphitheater ``gui-apps/hede`` bump then digests.

HeDE keeps its OWN version line (independent of gest's), so the tag version comes
from ``hede/CMakeLists.txt`` (``project(hede VERSION X.Y.Z)``) — NOT the GeST
release version. Modelled on ``release-overlay.py``: writes nothing unless ``--push``.

  packaging/mirror-hede.py [VERSION] [--push] [--repo URL]

VERSION defaults to the HeDE version in ``hede/CMakeLists.txt`` (a leading ``v``
is accepted). The push URL defaults to ``git@github.com:k5blazerfl/HeDE.git``
(override with ``--repo`` / ``$HEDE_REPO``); a dry run clones read-only over https.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HEDE_DIR = REPO_ROOT / "hede"
DEFAULT_PUSH_REPO = "git@github.com:k5blazerfl/HeDE.git"
DRYRUN_REPO = "https://github.com/k5blazerfl/HeDE.git"


def die(msg: str) -> None:
    print(f"mirror-hede: {msg}", file=sys.stderr)
    raise SystemExit(1)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True):
    return subprocess.run(cmd, cwd=cwd, check=check, text=True)


def hede_version() -> str:
    """HeDE's own version, from hede/CMakeLists.txt (independent of gest's)."""
    text = (HEDE_DIR / "CMakeLists.txt").read_text(encoding="utf-8")
    m = re.search(r"project\(hede\s+VERSION\s+(\d+\.\d+\.\d+)", text)
    if not m:
        die("could not read HeDE version from hede/CMakeLists.txt")
    return m.group(1)  # type: ignore[union-attr]


def norm_version(v: str) -> str:
    v = v.lstrip("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", v):
        die(f"expected X.Y.Z, got {v!r}")
    return v


def mirror(ver: str, push: bool, repo: str) -> int:
    tag = f"v{ver}"
    src = repo if push else DRYRUN_REPO
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "HeDE"
        run(["git", "clone", "--depth", "1", src, str(clone)])
        run(["git", "config", "user.name", "k5blazerfl"], cwd=clone)
        run(["git", "config", "user.email", "k5blazerfl@fastmail.com"], cwd=clone)

        # Make the working tree an exact copy of hede/ (minus VCS metadata), so
        # files deleted here are deleted there too. Preserve the HeDE repo's own
        # .git and any .github (its identity/CI live only in that repo).
        run([
            "rsync", "-a", "--delete",
            "--exclude", ".git/", "--exclude", ".github/",
            f"{HEDE_DIR}/", f"{clone}/",
        ])
        run(["git", "add", "-A"], cwd=clone)

        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=clone
        ).returncode != 0
        if not staged:
            print(f"mirror-hede: HeDE already matches hede/ — tagging {tag} only")
        else:
            run(["git", "commit", "-m", f"Mirror GeST {tag} (hede/ subtree)"], cwd=clone)

        # (Re)create the release tag on this mirror commit.
        run(["git", "tag", "-f", tag], cwd=clone)

        if not push:
            print(f"\nmirror-hede: DRY RUN — would push main + {tag} to {repo}")
            run(["git", "--no-pager", "log", "--oneline", "-1"], cwd=clone, check=False)
            run(["git", "--no-pager", "diff", "--cached", "--stat", "HEAD~1"],
                cwd=clone, check=False)
            return 0

        run(["git", "push", "origin", "HEAD:main"], cwd=clone)
        run(["git", "push", "-f", "origin", tag], cwd=clone)
        print(f"mirror-hede: pushed main + {tag} to {repo}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Mirror hede/ to the standalone HeDE repo.")
    ap.add_argument("version", nargs="?", help="release version (default: pyproject)")
    ap.add_argument("--push", action="store_true", help="push main + tag (else dry run)")
    ap.add_argument("--repo", default=os.environ.get("HEDE_REPO", DEFAULT_PUSH_REPO),
                    help="push URL for the HeDE repo")
    args = ap.parse_args()

    if not HEDE_DIR.is_dir():
        die(f"{HEDE_DIR} not found — run from the GeST repo")
    ver = norm_version(args.version or hede_version())
    return mirror(ver, args.push, args.repo)


if __name__ == "__main__":
    raise SystemExit(main())
