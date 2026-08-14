"""Pure adapter for the Software core module — models <-> plain property bags.

The row/detail converters take a model instance and return a plain dict (the
``a{sv}`` payload the D-Bus layer packs). They import nothing heavy, so they are
unit-testable with hand-built model instances — no Portage. The *live* functions
import ``reader`` (Portage) lazily, so importing this module stays Portage-free.

Streaming/pagination for the big lists (ListInstalled) is a follow-on; Phase 2
returns bounded/whole lists in one reply, which D-Bus handles fine.
"""

from __future__ import annotations

from typing import Any


def pkg_to_dict(p: Any) -> dict[str, Any]:
    """A Package -> summary property bag (installed / upgradable / world views)."""
    return {
        "cp": p.cp,
        "version": p.version,
        "slot": p.slot,
        "description": p.description,
        "repository": p.repository,
        "homepage": p.homepage,
        "installed": p.installed,
        "from_binary": p.from_binary,
        "world_member": p.world_member,
        "available_version": p.available_version,
        "upgradable": p.upgradable,
    }


def result_to_dict(r: Any) -> dict[str, Any]:
    """A SearchResult -> summary property bag (search / categories / provides)."""
    return {
        "cp": r.cp,
        "best_version": r.best_version,
        "description": r.description,
        "installed": r.installed,
        "installed_version": r.installed_version or "",
        "repository": r.repository,
    }


def detail_to_dict(d: Any) -> dict[str, Any]:
    """A PackageDetail -> the full property bag for GetDetail."""
    return {
        "cp": d.cp,
        "available_version": d.available_version,
        "installed_version": d.installed_version,
        "slot": d.slot,
        "license": d.license,
        "homepage": d.homepage,
        "description": d.description,
        "keywords": d.keywords,
        "installed_size": d.installed_size,
        "download_size": d.download_size,
        "from_binary": d.from_binary,
        "required_by": list(d.required_by),
        "repository": d.repository,
        "other_repos": list(d.other_repos),
    }


# --- live functions (import Portage lazily) --------------------------------

def list_installed() -> list[dict[str, Any]]:
    from gest.core.software import reader
    return [pkg_to_dict(p) for p in reader.list_installed()]


def list_upgradable() -> list[dict[str, Any]]:
    from gest.core.software import reader
    return [pkg_to_dict(p) for p in reader.list_upgradable()]


def search(term: str, fields: list[str], mode: str,
           ignore_case: bool, limit: int) -> list[dict[str, Any]]:
    from gest.core.software import reader
    results = reader.search(term, fields=tuple(fields) or ("name",),
                            mode=mode, ignore_case=ignore_case, limit=limit or 200)
    return [result_to_dict(r) for r in results]


def packages_in_category(category: str, limit: int) -> list[dict[str, Any]]:
    from gest.core.software import reader
    return [result_to_dict(r) for r in reader.packages_in_category(category, limit=limit or 500)]


def list_categories() -> list[str]:
    from gest.core.software import reader
    return reader.list_categories()


def get_detail(cp: str) -> dict[str, Any]:
    from gest.core.software import reader
    detail = reader.get_package_detail(cp)
    return detail_to_dict(detail) if detail is not None else {}


def counts() -> dict[str, int]:
    from gest.core.software import reader
    return dict(reader.counts())
