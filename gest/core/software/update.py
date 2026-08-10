"""System Update planning — turn ``emerge --pretend -uDN @world`` into data.

``emerge --pretend`` is read-only, so like the other previews it runs as the
invoking user. Its output buries the useful ``[ebuild …]`` merge list in
dependency-resolution noise; this module parses that list into structured
changes — each with an action (new / update / rebuild), the old→new version and
the download size — plus the totals, so the UI can show a compact table instead
of the raw dump. Pure parsing (given output text) is CI-testable.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

_EMERGE = shutil.which("emerge") or "/usr/bin/emerge"

Runner = Callable[[list[str]], "tuple[int, str]"]

# One merge-list line, e.g.
#   [ebuild     U  ] app-arch/gzip-1.14::gentoo [1.13]  USE="..." 420 KiB
#   [ebuild  N     ] dev-libs/newdep-2.0::gentoo  USE="..." 1,200 KiB
#   [binary   R    ] app-crypt/libsecret-0.21.7::gentoo  USE="..." 0 KiB
_MERGE_RE = re.compile(
    r"^\[(?P<type>ebuild|binary)\s+(?P<flags>[^\]]*)\]\s+(?P<atom>\S+)"
    r"(?:\s+\[(?P<old>[^\]]+)\])?"
    r".*?(?P<size>[\d,]+(?:\.\d+)?)\s+(?P<unit>KiB|MiB|GiB|TiB|B)\s*$")

# Split "category/name-version" into (cp, version): the version starts at the
# first '-' followed by a digit (standard Gentoo atom shape).
_CPV_RE = re.compile(r"^(?P<cp>.+?)-(?P<ver>\d\S*)$")

_UNITS = {"B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "TiB": 1024 ** 4}

# Action → the glyph the UI shows in the lead column.
NEW, UPDATE, REBUILD = "new", "update", "rebuild"


@dataclass(slots=True)
class Change:
    """One package emerge would merge for the update."""

    cp: str
    old_version: str
    new_version: str
    action: str            # new | update | rebuild
    binary: bool = False
    size: int = 0          # download size in bytes

    @property
    def category(self) -> str:
        return self.cp.split("/", 1)[0]

    @property
    def package(self) -> str:
        return self.cp.split("/", 1)[1] if "/" in self.cp else self.cp


@dataclass(slots=True)
class UpdatePlan:
    changes: list[Change] = field(default_factory=list)
    ok: bool = True
    error: str = ""

    @property
    def total_download(self) -> int:
        return sum(c.size for c in self.changes)

    def counts(self) -> dict[str, int]:
        out = {NEW: 0, UPDATE: 0, REBUILD: 0}
        for c in self.changes:
            out[c.action] = out.get(c.action, 0) + 1
        return out


def _default_runner(argv: list[str]) -> tuple[int, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout
    if proc.stderr:
        out = f"{out}\n{proc.stderr}" if out else proc.stderr
    return proc.returncode, out


def split_cpv(atom: str) -> tuple[str, str]:
    """Split ``category/name-version`` into ``(cp, version)`` (best-effort)."""
    m = _CPV_RE.match(atom)
    return (m.group("cp"), m.group("ver")) if m else (atom, "")


def _to_bytes(num: str, unit: str) -> int:
    return int(float(num.replace(",", "")) * _UNITS.get(unit, 1))


def parse_changes(output: str) -> list[Change]:
    """Extract the ``[ebuild …]`` merge list from update --pretend output."""
    changes: list[Change] = []
    for line in output.splitlines():
        m = _MERGE_RE.match(line.strip())
        if not m:
            continue
        cp, new_ver = split_cpv(m.group("atom").split("::", 1)[0])
        old = (m.group("old") or "").strip()
        if "N" in m.group("flags"):
            action = NEW
        elif old:
            action = UPDATE
        else:
            action = REBUILD
        changes.append(Change(
            cp=cp, old_version=old, new_version=new_ver, action=action,
            binary=m.group("type") == "binary",
            size=_to_bytes(m.group("size"), m.group("unit"))))
    return changes


def _first_error(output: str) -> str:
    for line in output.splitlines():
        s = line.strip()
        if s.startswith("!!!") or "error" in s.lower():
            return s.lstrip("! ").strip()
    return ""


def plan_update(*, runner: Runner | None = None) -> UpdatePlan:
    """Run ``emerge --pretend -uDN @world`` and return the parsed change list."""
    run = runner or _default_runner
    rc, out = run([_EMERGE, "--pretend", "--verbose", "--color", "n",
                   "-uDN", "@world"])
    if rc != 0:
        return UpdatePlan(ok=False,
                          error=_first_error(out) or "emerge could not resolve @world")
    return UpdatePlan(changes=parse_changes(out), ok=True)


# Live merge markers, e.g. ">>> Emerging (2 of 5) app-editors/vim-9.1::gentoo"
# and ">>> Installing (2 of 5) app-editors/vim-9.1::gentoo" (also "Emerging binary").
_PROGRESS_RE = re.compile(
    r">>> (?P<phase>Emerging|Installing)(?: binary)? "
    r"\((?P<n>\d+) of (?P<total>\d+)\)\s+(?P<atom>\S+)")


@dataclass(slots=True)
class MergeProgress:
    phase: str            # "Emerging" (building) | "Installing" (merging to live)
    n: int
    total: int
    atom: str             # category/name-version (::repo stripped)


def parse_merge_progress(line: str) -> MergeProgress | None:
    """Parse an emerge ``>>> Emerging/Installing (N of M) <atom>`` line, else None."""
    m = _PROGRESS_RE.search(line)
    if not m:
        return None
    return MergeProgress(m.group("phase"), int(m.group("n")), int(m.group("total")),
                         m.group("atom").split("::", 1)[0])


def human_size(n: int) -> str:
    """Format a byte count like '2.1 MiB' ('—' when zero/unknown)."""
    if n <= 0:
        return "—"
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"
