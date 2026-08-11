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


# -- staged custom-set edits (mark now, apply on Accept) --------------------

NEW = "new"
MODIFY = "modify"
DELETE = "delete"


@dataclass(slots=True, frozen=True)
class SetEdit:
    """One staged custom-set change. ``kind`` is NEW / MODIFY / DELETE; ``atoms``
    is the desired member list (empty for a delete)."""

    name: str
    kind: str
    atoms: list[str] = field(default_factory=list)


class PendingSets:
    """Staged custom-set edits over an on-disk baseline (pure, CI-testable).

    Mirrors :mod:`gest.core.repos.pending`: edits accumulate here and are applied
    together on Accept. ``disk`` maps a set name → its on-disk atoms. An edit
    either sets a name's atoms (a *create* if the name isn't on disk, else a
    *modify*) or deletes an on-disk set. Editing a set back to its baseline
    clears the change; deleting a never-saved staged set just drops it — so the
    store only ever holds genuine, minimal differences from disk.
    """

    def __init__(self, disk: dict[str, list[str]] | None = None) -> None:
        self._disk: dict[str, list[str]] = disk or {}
        self._atoms: dict[str, list[str]] = {}    # staged create / modify
        self._deleted: set[str] = set()           # staged deletions

    def rebase(self, disk: dict[str, list[str]]) -> None:
        """Point at a fresh on-disk snapshot, keeping the staged edits."""
        self._disk = disk

    # -- queries ------------------------------------------------------------

    def is_empty(self) -> bool:
        return not self._atoms and not self._deleted

    def count(self) -> int:
        return len(self._atoms) + len(self._deleted)

    def all_names(self) -> list[str]:
        """Every custom set to display: on-disk plus staged-new, sorted."""
        return sorted(set(self._disk) | set(self._atoms) | self._deleted)

    def exists(self, name: str) -> bool:
        return name in self._disk or name in self._atoms

    def is_new(self, name: str) -> bool:
        return name in self._atoms and name not in self._disk

    def is_deleted(self, name: str) -> bool:
        return name in self._deleted

    def is_modified(self, name: str) -> bool:
        return name in self._atoms or name in self._deleted

    def base_atoms(self, name: str) -> list[str]:
        return self._disk.get(name, [])

    def working_atoms(self, name: str) -> list[str] | None:
        """Atoms after staged edits — ``None`` if the set is staged for delete."""
        if name in self._deleted:
            return None
        return self._atoms.get(name) or self._disk.get(name, [])

    # -- mutations ----------------------------------------------------------

    def set_atoms(self, name: str, atoms: list[str]) -> None:
        """Stage ``name`` to hold ``atoms`` (create or modify)."""
        self._deleted.discard(name)               # editing un-deletes
        if name in self._disk and atoms == self._disk[name]:
            self._atoms.pop(name, None)           # back to unmodified
        else:
            self._atoms[name] = list(atoms)

    def toggle_delete(self, name: str) -> None:
        """Stage/unstage deletion. Deleting a never-saved new set cancels it."""
        if name in self._deleted:
            self._deleted.discard(name)
        elif self.is_new(name):
            self._atoms.pop(name, None)           # cancel the staged create
        elif name in self._disk:
            self._atoms.pop(name, None)
            self._deleted.add(name)

    def clear(self) -> None:
        self._atoms.clear()
        self._deleted.clear()

    # -- apply --------------------------------------------------------------

    def edits(self) -> list[SetEdit]:
        """The staged changes as :class:`SetEdit`\\ s, sorted by name."""
        out = [SetEdit(n, NEW if n not in self._disk else MODIFY, list(a))
               for n, a in self._atoms.items()]
        out += [SetEdit(n, DELETE) for n in self._deleted]
        return sorted(out, key=lambda e: e.name)
