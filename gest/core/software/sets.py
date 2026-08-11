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
import re
from dataclasses import dataclass, field

from gest.core.software.world import valid_atom

SETS_DIR = "/etc/portage/sets"

# A custom set's file name (the part after the @), and a @set reference that a
# set file may contain alongside plain package atoms.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._-]*$")
_REF_RE = re.compile(r"^@[A-Za-z0-9][A-Za-z0-9+._-]*$")

# A header line GeST writes so a set can be empty (an empty file would mean
# "delete") and so hand-editors see where it came from.
SET_HEADER = "# GeST-managed package set — one atom (or @set) per line"

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


# -- editing custom sets ----------------------------------------------------

def valid_set_name(name: str) -> bool:
    """True if ``name`` is a safe custom-set file name (the part after @)."""
    return bool(_NAME_RE.match(name))


def valid_entry(entry: str) -> bool:
    """True if ``entry`` is a valid set member: a package atom or a @set ref."""
    return valid_atom(entry) or bool(_REF_RE.match(entry))


def set_path(name: str, sets_dir: str = SETS_DIR) -> str:
    """The on-disk path of the custom set called ``name`` (no leading @)."""
    return os.path.join(sets_dir, name)


def render_set(atoms) -> str:
    """The file body for a custom set holding ``atoms`` (always non-empty)."""
    return "\n".join([SET_HEADER, *atoms]) + "\n"
