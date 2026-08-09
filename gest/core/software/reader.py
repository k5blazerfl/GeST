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

import contextlib
import functools
import os
import re

import portage
from portage.dep import Atom, dep_getkey, use_reduce
from portage.versions import cpv_getkey, cpv_getversion
from portage.xml.metadata import MetaDataXML

from gest.core.software.model import Package, PackageDetail, SearchResult, UseFlag

# Portage's trees for the running root. ``portage.db`` is keyed by root ("/").
_ROOT = portage.root
_TREES = portage.db[_ROOT]
_VARDB = _TREES["vartree"].dbapi  # installed packages
_PORTDB = _TREES["porttree"].dbapi  # ebuilds available in repos

# aux_get keys we care about (available in both dbs).
_INST_KEYS = ("DESCRIPTION", "SLOT", "repository", "IUSE", "USE", "HOMEPAGE")
# Extra keys for the detail pane (available in both dbs).
_DETAIL_KEYS = (
    "DESCRIPTION", "SLOT", "repository", "IUSE", "USE", "HOMEPAGE",
    "LICENSE", "KEYWORDS",
)


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


def _installed_from_binary(cpv: str) -> bool:
    """True if the installed ``cpv`` was merged from a binary package.

    Portage stamps BUILD_ID (and BINPKGMD5) into the VDB only for packages that
    came from a binpkg; a source build has neither.
    """
    return bool(_VARDB.aux_get(cpv, ("BUILD_ID",))[0])


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
                from_binary=_installed_from_binary(cpv),
                world_member=cp in world,
                use_flags=_parse_use_flags(iuse, use),
            )
        )
    return packages


# Search-in fields that require reading package metadata → their aux_get key.
_META_FIELD_KEYS = {"summary": "DESCRIPTION", "homepage": "HOMEPAGE", "license": "LICENSE"}


@functools.lru_cache(maxsize=4096)
def _longdescription(cp: str) -> str:
    """The package's metadata.xml <longdescription>, or "" (time-consuming).

    Cached per cp; parses the ebuild's metadata.xml. Almost always empty in
    Gentoo, so this is the slow, opt-in search path.
    """
    cp = portage.dep_getkey(cp) if "/" in cp else cp
    cpv = _best_available(cp)
    if not cpv:
        inst = _VARDB.cp_list(cp)
        cpv = inst[-1] if inst else ""
    if not cpv:
        return ""
    try:
        ebuild, _repo = _PORTDB.findname2(cpv)
        if not ebuild:
            return ""
        meta = os.path.join(os.path.dirname(ebuild), "metadata.xml")
        descs = MetaDataXML(meta, None).descriptions()
    except Exception:
        return ""
    return " ".join(d.strip() for d in (descs or []) if d and d.strip())


def _make_matcher(term: str, mode: str, ignore_case: bool):
    """Return a predicate ``matches(text) -> bool`` for the given search mode."""
    if mode == "regexp":
        try:
            pattern = re.compile(term, re.IGNORECASE if ignore_case else 0)
        except re.error:
            return None
        return lambda text: bool(pattern.search(text or ""))
    needle = term.lower() if ignore_case else term

    def norm(text: str) -> str:
        return (text or "").lower() if ignore_case else (text or "")

    if mode == "exact":
        return lambda text: norm(text) == needle
    return lambda text: needle in norm(text)  # "contains" (default)


def search(
    term: str,
    *,
    fields: tuple[str, ...] = ("name",),
    mode: str = "contains",
    ignore_case: bool = True,
    limit: int = 200,
) -> list[SearchResult]:
    """Search packages by name and/or metadata fields.

    ``fields`` chooses what to match: ``"name"`` (category/package, cheap) plus
    any of ``"summary"``/``"homepage"``/``"license"`` (a single per-package
    ``aux_get`` read — the "time-consuming" part, only paid when requested and
    always run off the UI thread). ``mode`` is ``"contains"`` (substring),
    ``"exact"`` (whole name/field equals the phrase) or ``"regexp"``.
    """
    term = term.strip()
    if not term:
        return []
    matches = _make_matcher(term, mode, ignore_case)
    if matches is None:  # invalid regexp
        return []

    want_name = "name" in fields
    meta_fields = [f for f in fields if f in _META_FIELD_KEYS]
    want_meta = bool(meta_fields)
    want_desc = "description" in fields
    results: list[SearchResult] = []

    for cp in _PORTDB.cp_all():
        name_hit = False
        if want_name:
            name_hit = matches(cp) or (mode == "exact" and matches(cp.split("/")[-1]))
        if not name_hit and not want_meta and not want_desc:
            continue  # name-only search skips the expensive metadata read
        best = _best_available(cp)
        version = cpv_getversion(best) if best else ""
        values: dict[str, str] = {}
        if best:
            # DESCRIPTION is always read (shown as the row summary); add the
            # other requested metadata keys.
            keys = ["DESCRIPTION", *[_META_FIELD_KEYS[f] for f in meta_fields
                                     if _META_FIELD_KEYS[f] != "DESCRIPTION"]]
            try:
                got = _PORTDB.aux_get(best, keys)
                values = dict(zip(keys, got, strict=True))
            except Exception:
                # A broken ebuild (e.g. in a third-party overlay) can make
                # aux_get raise; don't let one bad package sink the whole search.
                values = {}
        desc = values.get("DESCRIPTION", "")
        hit = name_hit
        if not hit:
            for field in meta_fields:
                if matches(values.get(_META_FIELD_KEYS[field], "")):
                    hit = True
                    break
        if not hit and want_desc and matches(_longdescription(cp)):
            hit = True
        if not hit:
            continue
        inst = _VARDB.cp_list(cp)
        inst_ver = cpv_getversion(inst[-1]) if inst else None
        results.append(SearchResult(cp, version, desc, inst_ver))
        if len(results) >= limit:
            break
    results.sort(key=lambda r: r.cp)
    return results


def search_file_owner(path: str) -> list[SearchResult]:
    """Installed package(s) that own a given file path (the qfile concept).

    Uses the vardb CONTENTS owner index; only installed packages have file
    lists, so this is installed-only. Needs an absolute path.
    """
    if not path.startswith("/"):
        return []
    try:
        owners = _VARDB._owners.get_owners([path])
    except Exception:
        return []
    results: list[SearchResult] = []
    seen: set[str] = set()
    for dblink in owners:
        cpv = dblink.mycpv
        cp = cpv_getkey(cpv)
        if cp in seen:
            continue
        seen.add(cp)
        version = cpv_getversion(cpv)
        try:
            desc = _VARDB.aux_get(cpv, ["DESCRIPTION"])[0]
        except Exception:
            desc = ""
        results.append(SearchResult(cp, version, desc, version))
    results.sort(key=lambda r: r.cp)
    return results


def list_categories() -> list[str]:
    """Every Portage category (the Gentoo analogue of YaST 'package groups')."""
    return sorted(_PORTDB.categories)


def packages_in_category(category: str, *, limit: int = 500) -> list[SearchResult]:
    """Available packages within one category, as lightweight search hits."""
    prefix = f"{category}/"
    results: list[SearchResult] = []
    for cp in _PORTDB.cp_all():
        if not cp.startswith(prefix):
            continue
        best = _best_available(cp)
        version = cpv_getversion(best) if best else ""
        desc = ""
        if best:
            try:
                desc = _PORTDB.aux_get(best, ["DESCRIPTION"])[0]
            except Exception:
                desc = ""
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
        from_binary=installed and _installed_from_binary(cpv),
        world_member=cp in world,
        use_flags=_parse_use_flags(iuse, use),
    )


def counts() -> dict[str, int]:
    """Cheap summary numbers for the module's landing view."""
    return {
        "installed": len(_VARDB.cpv_all()),
        "world": len(_world_atoms()),
    }


# -- package facts: size + reverse dependencies -------------------------------

_DEP_KEYS = ("RDEPEND", "DEPEND", "BDEPEND", "PDEPEND")


def _human_bytes(n: int) -> str:
    """Human-readable byte size (B / KiB / MiB / GiB)."""
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


def installed_size(cp: str) -> int:
    """Total on-disk size (bytes) of the installed version, else 0."""
    cp = portage.dep_getkey(cp) if "/" in cp else cp
    inst = _VARDB.cp_list(cp)
    if not inst:
        return 0
    try:
        contents = _VARDB._dblink(inst[-1]).getcontents()
    except Exception:
        return 0
    total = 0
    for path in contents:
        with contextlib.suppress(OSError):
            total += os.lstat(path).st_size
    return total


def download_size(cp: str) -> int:
    """Total distfile download size (bytes) for the best available version."""
    cp = portage.dep_getkey(cp) if "/" in cp else cp
    best = _best_available(cp)
    if not best:
        return 0
    try:
        return sum(_PORTDB.getfetchsizes(best).values())
    except Exception:
        return 0


@functools.lru_cache(maxsize=1)
def _reverse_index() -> dict[str, frozenset[str]]:
    """Map each cp to the set of *installed* packages that depend on it.

    Built once per session from the installed packages' dependency strings
    (USE-flattened to the superset). Blockers are ignored. Cleared by
    ``invalidate_caches`` after a merge/unmerge.
    """
    idx: dict[str, set[str]] = {}
    for cpv in _VARDB.cpv_all():
        dependent = cpv_getkey(cpv)
        for dep in _VARDB.aux_get(cpv, _DEP_KEYS):
            if not dep:
                continue
            try:
                tokens = use_reduce(dep, matchall=True, flat=True, token_class=Atom)
            except Exception:
                continue
            for tok in tokens:
                if isinstance(tok, Atom) and not tok.blocker:
                    idx.setdefault(dep_getkey(str(tok)), set()).add(dependent)
    return {key: frozenset(deps) for key, deps in idx.items()}


def reverse_dependencies(cp: str) -> list[str]:
    """Installed packages that depend on ``cp`` (sorted)."""
    cp = portage.dep_getkey(cp) if "/" in cp else cp
    return sorted(_reverse_index().get(cp, ()))


def invalidate_caches() -> None:
    """Drop cached indexes after a mutation (merge/unmerge) so they rebuild."""
    _reverse_index.cache_clear()
    _world_atoms.cache_clear()


def get_package_detail(cp: str) -> PackageDetail | None:
    """Metadata for the detail pane: best-available + installed versions.

    Reads from the ebuild tree when an ebuild exists (freshest metadata),
    otherwise from the installed copy. Returns None if the package is unknown.
    """
    cp = portage.dep_getkey(cp) if "/" in cp else cp
    inst = _VARDB.cp_list(cp)
    avail = _best_available(cp)
    if avail:
        src_db, src_cpv = _PORTDB, avail
    elif inst:
        src_db, src_cpv = _VARDB, inst[-1]
    else:
        return None
    desc, slot, _repo, _iuse, _use, homepage, lic, kw = src_db.aux_get(src_cpv, _DETAIL_KEYS)
    return PackageDetail(
        cp=cp,
        available_version=cpv_getversion(avail) if avail else "",
        installed_version=cpv_getversion(inst[-1]) if inst else "",
        slot=slot,
        license=lic,
        homepage=homepage,
        description=desc,
        keywords=kw,
        installed_size=installed_size(cp),
        download_size=download_size(cp),
        from_binary=bool(inst) and _installed_from_binary(inst[-1]),
        required_by=reverse_dependencies(cp),
    )
