"""Pure, validated argv builders for kernel building.

``genkernel all``, manual ``make`` targets on a source tree, and a dracut
initramfs. These run as root, so every path/version/jobs value is validated here
before it can reach a shell; the builders are pure and CI-testable.
"""

from __future__ import annotations

import re

# An absolute path with no newline/NUL (a source dir or a kernel .config file).
# A kernel version string (dracut --kver): 6.6.30-gentoo, etc.
_KVER_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._+-]*\Z")

MAX_JOBS = 512
MAKE_TARGETS = frozenset({"", "modules_install", "install"})


def _valid_path(path: str) -> bool:
    return path.startswith("/") and "\n" not in path and "\0" not in path and ".." not in path


def _require_jobs(jobs: int) -> int:
    if not 1 <= jobs <= MAX_JOBS:
        raise ValueError(f"invalid job count: {jobs!r}")
    return jobs


def genkernel_argv(*, kernel_config: str = "", genkernel: str = "genkernel") -> list[str]:
    """`genkernel [--kernel-config=<file>] all` — the automated build path."""
    argv = [genkernel]
    if kernel_config:
        if not _valid_path(kernel_config):
            raise ValueError(f"invalid kernel config path: {kernel_config!r}")
        argv.append(f"--kernel-config={kernel_config}")
    argv.append("all")
    return argv


def make_argv(
    target: str = "", *, jobs: int = 1, directory: str = "/usr/src/linux", make: str = "make"
) -> list[str]:
    """`make -C <dir> -j<n> [target]` for a manual build/modules_install/install."""
    if not _valid_path(directory):
        raise ValueError(f"invalid source directory: {directory!r}")
    if target not in MAKE_TARGETS:
        raise ValueError(f"unsupported make target: {target!r}")
    argv = [make, "-C", directory, f"-j{_require_jobs(jobs)}"]
    if target:
        argv.append(target)
    return argv


def dracut_argv(kver: str = "", *, force: bool = True, dracut: str = "dracut") -> list[str]:
    """`dracut [--force] [--kver <version>]` — build an initramfs."""
    argv = [dracut]
    if force:
        argv.append("--force")
    if kver:
        if not _KVER_RE.match(kver):
            raise ValueError(f"invalid kernel version: {kver!r}")
        argv += ["--kver", kver]
    return argv
