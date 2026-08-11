"""Portage package sets: enumerate curated sets and resolve their members.

Beyond the world set, Portage groups packages into *sets*: built-in ones like
@system (what the base system needs) and @profile (what your profile pulls in),
plus custom sets you define as plain atom files under /etc/portage/sets. This
module lists those and resolves their members so the frontend can browse them.

Reading is unprivileged. Custom sets are parsed purely from their files (so the
parser is CI-testable without Portage); the built-in sets are resolved through
the Portage sets API, which is wrapped best-effort so a query failure yields an
empty set rather than crashing the browser. Portage exposes many internal
rebuild sets (@security, @changed-deps, …) that are noise here — only the two
user-meaningful built-ins are surfaced.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

SETS_DIR = "/etc/portage/sets"

# Built-in sets worth browsing → one-line description. Order is display order.
_BUILTIN = (
    ("system", "Core packages the base system requires"),
    ("profile", "Packages pulled in by your selected profile"),
)


@dataclass(slots=True)
class PackageSet:
    name: str                                   # display name, e.g. "@system"
    atoms: list[str] = field(default_factory=list)
    description: str = ""
    kind: str = "builtin"                       # "builtin" | "custom"


def read_set_file(path: str) -> list[str]:
    """Parse a custom set file into its atoms (pure). Blank/# lines are skipped."""
    atoms: list[str] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if line and not line.startswith("#"):
                    atoms.append(line)
    except OSError:
        pass
    return atoms


def custom_sets(sets_dir: str = SETS_DIR) -> list[PackageSet]:
    """Custom sets defined as files under ``sets_dir`` (pure; @<filename>)."""
    try:
        names = sorted(
            n for n in os.listdir(sets_dir)
            if not n.startswith(".") and os.path.isfile(os.path.join(sets_dir, n)))
    except OSError:
        return []                               # no /etc/portage/sets — that's fine
    return [
        PackageSet(name=f"@{n}", kind="custom",
                   atoms=read_set_file(os.path.join(sets_dir, n)),
                   description=f"Custom set · {sets_dir}/{n}")
        for n in names
    ]


def _builtin_atoms(name: str) -> list[str]:
    """Members of a built-in set via the Portage sets API (best-effort)."""
    try:
        import portage
        from portage._sets import load_default_config
        sc = load_default_config(portage.settings, portage.db[portage.root])
        return sorted(str(a) for a in sc.getSetAtoms(name))
    except Exception:                           # pragma: no cover - depends on portage
        return []


def builtin_sets() -> list[PackageSet]:
    """The curated built-in sets (@system, @profile) with their members."""
    return [PackageSet(name=f"@{name}", kind="builtin",
                       atoms=_builtin_atoms(name), description=desc)
            for name, desc in _BUILTIN]


def list_sets(sets_dir: str = SETS_DIR) -> list[PackageSet]:
    """All browsable sets: the built-ins, then any custom sets on disk."""
    return builtin_sets() + custom_sets(sets_dir)
