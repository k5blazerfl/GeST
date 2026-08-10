"""Clean Up (depclean) planning — turn ``emerge --pretend --depclean`` into data.

``emerge --pretend --depclean`` is read-only, so like the rest of the previews
it runs as the invoking user (not through the privileged backend). Its output is
noisy — a safety lecture and, with ``--verbose``, a "pulled in by" block for every
*kept* package. This module drops ``--verbose`` and parses the small useful part:
the list of orphaned packages that would be unmerged, plus the summary counts. It
also looks up each orphan's on-disk size from the vdb so the UI can show how much
space a clean-up reclaims. Pure parsing (given output text) is CI-testable.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

_EMERGE = shutil.which("emerge") or "/usr/bin/emerge"
_VDB = "/var/db/pkg"

Runner = Callable[[list[str]], "tuple[int, str]"]

# A bare category/name line inside the unmerge list (e.g. " app-arch/innoextract").
_CP_RE = re.compile(r"\A[a-z0-9][a-z0-9+._-]*/[a-zA-Z0-9+._-]+\Z")
_SEL_RE = re.compile(r"\Aselected:\s*(?P<ver>\S+)")
_UNMERGE_MARK = "These are the packages that would be unmerged"
_END_MARK = "All selected packages"
# The summary block at the tail: "Packages installed:   1200", etc.
_COUNTS = {
    "installed": "Packages installed",
    "world": "Packages in world",
    "system": "Packages in system",
    "required": "Required packages",
    "to_remove": "Number to remove",
}


@dataclass(slots=True)
class Orphan:
    """One package depclean would remove."""

    cp: str                 # category/name
    version: str = ""
    size: int = 0           # installed size in bytes (0 = unknown)

    @property
    def category(self) -> str:
        return self.cp.split("/", 1)[0]

    @property
    def package(self) -> str:
        return self.cp.split("/", 1)[1] if "/" in self.cp else self.cp


@dataclass(slots=True)
class CleanupPlan:
    orphans: list[Orphan] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    ok: bool = True
    error: str = ""

    @property
    def total_size(self) -> int:
        return sum(o.size for o in self.orphans)


def _default_runner(argv: list[str]) -> tuple[int, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout
    if proc.stderr:
        out = f"{out}\n{proc.stderr}" if out else proc.stderr
    return proc.returncode, out


def parse_orphans(output: str) -> list[Orphan]:
    """Extract the packages emerge would unmerge from depclean --pretend output."""
    orphans: list[Orphan] = []
    in_list = False
    current: Orphan | None = None
    for line in output.splitlines():
        s = line.strip()
        if not in_list:
            if _UNMERGE_MARK in s:
                in_list = True
            continue
        if s.startswith(_END_MARK) or s.startswith(">>>"):
            break
        if _CP_RE.match(s):
            current = Orphan(cp=s)
            orphans.append(current)
        elif current is not None and (m := _SEL_RE.match(s)):
            current.version = m.group("ver")
    return orphans


def parse_counts(output: str) -> dict[str, int]:
    """Extract the trailing summary counts (installed / world / to_remove / …)."""
    counts: dict[str, int] = {}
    for line in output.splitlines():
        s = line.strip()
        for key, label in _COUNTS.items():
            if s.startswith(label) and (m := re.search(r"(\d+)\s*\Z", s)):
                counts[key] = int(m.group(1))
    return counts


def _first_error(output: str) -> str:
    for line in output.splitlines():
        s = line.strip()
        if s.startswith("!!!") or "error" in s.lower():
            return s.lstrip("! ").strip()
    return ""


def installed_size(orphan: Orphan, vdb: str = _VDB) -> int:
    """The orphan's installed size in bytes, from its vdb ``SIZE`` file (0 if n/a)."""
    if not orphan.version:
        return 0
    path = os.path.join(vdb, orphan.category,
                        f"{orphan.package}-{orphan.version}", "SIZE")
    try:
        with open(path, encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return 0


def plan_cleanup(*, runner: Runner | None = None, vdb: str = _VDB) -> CleanupPlan:
    """Run depclean --pretend and return the orphan list + counts (+ sizes)."""
    run = runner or _default_runner
    rc, out = run([_EMERGE, "--pretend", "--color", "n", "--depclean"])
    counts = parse_counts(out)
    if rc != 0:
        return CleanupPlan(counts=counts, ok=False,
                           error=_first_error(out) or "emerge could not resolve dependencies")
    orphans = parse_orphans(out)
    for orphan in orphans:
        orphan.size = installed_size(orphan, vdb)
    return CleanupPlan(orphans=orphans, counts=counts, ok=True)


def human_size(n: int) -> str:
    """Format a byte count like '2.1 MiB' ('—' when unknown)."""
    if n <= 0:
        return "—"
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"
