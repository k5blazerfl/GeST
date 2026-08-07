"""Read-only Portage queries via the in-process Portage Python API.

Everything here runs as the invoking (unprivileged) user and never mutates the
system. We deliberately use the API — ``portdbapi`` / ``vartree`` — rather than
scraping ``emerge`` output, so results are structured and stable.

Note: we avoid ``portdbapi.xmatch``/``.match`` here. Those drive an asyncio loop
internally (``run_until_complete``), which is unsafe to call from inside an
already-running event loop such as the TUI's. The synchronous ``cp_list`` +
``versions.best`` path gives us a stable "best available" version instead.
"""

from __future__ import annotations

import functools
import os

import portage
from portage.versions import cpv_getkey, cpv_getversion

from gest.core.software.model import Package, SearchResult, UseFlag

# Portage's trees for the running root. ``portage.db`` is keyed by root ("/").
_ROOT = portage.root
_TREES = portage.db[_ROOT]
_VARDB = _TREES["vartree"].dbapi  # installed packages
_PORTDB = _TREES["porttree"].dbapi  # ebuilds available in repos

# aux_get keys we care about (available in both dbs).
_INST_KEYS = ("DESCRIPTION", "SLOT", "repository", "IUSE", "USE", "HOMEPAGE")


@functools.lru_cache(maxsize=1)
def _world_atoms() -> frozenset[str]:
    """The set of package cp's explicitly recorded in the world file."""
    world_file = os.path.join(portage.settings["EROOT"], portage.const.WORLD_FILE)
    atoms: set[str] = set()
    try:
        with open(world_file, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if line and not line.startswith("#"):
                    atoms.add(portage.dep_getkey(line) if "/" in line else line)
    except OSError:
        pass
    return frozenset(atoms)


def _is_live(version: str) -> bool:
    """A live/scm ebuild (version 9999...) — excluded from 'best available'."""
    return version.startswith("9999")


def _best_available(cp: str) -> str:
    """Highest non-live available cpv for ``cp`` (sync; no asyncio loop)."""
    cpvs = _PORTDB.cp_list(cp)
    if not cpvs:
        return ""
    stable = [c for c in cpvs if not _is_live(cpv_getversion(c))]
    return portage.versions.best(stable or cpvs)


def _parse_use_flags(iuse: str, use: str) -> list[UseFlag]:
    """Combine IUSE (available, may carry +/- defaults) with USE (enabled)."""
    enabled = set(use.split())
    flags: list[UseFlag] = []
    seen: set[str] = set()
    for token in iuse.split():
        name = token.lstrip("+-")
        if name in seen:
            continue
        seen.add(name)
        flags.append(UseFlag(name=name, enabled=name in enabled))
    return sorted(flags, key=lambda f: f.name)


def list_installed() -> list[Package]:
    """Every installed package version, sorted by cp."""
    world = _world_atoms()
    packages: list[Package] = []
    for cpv in sorted(_VARDB.cpv_all()):
        cp = cpv_getkey(cpv)
        desc, slot, repo, iuse, use, homepage = _VARDB.aux_get(cpv, _INST_KEYS)
        packages.append(
            Package(
                cp=cp,
                version=cpv_getversion(cpv),
                slot=slot,
                description=desc,
                repository=repo,
                homepage=homepage,
                installed=True,
                world_member=cp in world,
                use_flags=_parse_use_flags(iuse, use),
            )
        )
    return packages


def search(term: str, limit: int = 200) -> list[SearchResult]:
    """Substring search over available package names (category/package)."""
    needle = term.strip().lower()
    if not needle:
        return []
    results: list[SearchResult] = []
    for cp in _PORTDB.cp_all():
        if needle not in cp.lower():
            continue
        best = _best_available(cp)
        version = cpv_getversion(best) if best else ""
        desc = _PORTDB.aux_get(best, ["DESCRIPTION"])[0] if best else ""
        inst = _VARDB.cp_list(cp)
        inst_ver = cpv_getversion(inst[-1]) if inst else None
        results.append(SearchResult(cp, version, desc, inst_ver))
        if len(results) >= limit:
            break
    results.sort(key=lambda r: r.cp)
    return results


def get_package(cp: str) -> Package | None:
    """Detailed view of a package by cp, preferring the installed version.

    Falls back to the best available ebuild when nothing is installed.
    """
    cp = portage.dep_getkey(cp) if "/" in cp else cp
    world = _world_atoms()

    inst = _VARDB.cp_list(cp)
    if inst:
        cpv = inst[-1]
        db = _VARDB
        installed = True
    else:
        cpv = _best_available(cp)
        if not cpv:
            return None
        db = _PORTDB
        installed = False

    desc, slot, repo, iuse, use, homepage = db.aux_get(cpv, _INST_KEYS)
    return Package(
        cp=cp,
        version=cpv_getversion(cpv),
        slot=slot,
        description=desc,
        repository=repo,
        homepage=homepage,
        installed=installed,
        world_member=cp in world,
        use_flags=_parse_use_flags(iuse, use),
    )


def counts() -> dict[str, int]:
    """Cheap summary numbers for the module's landing view."""
    return {
        "installed": len(_VARDB.cpv_all()),
        "world": len(_world_atoms()),
    }
