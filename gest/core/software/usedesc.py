"""USE-flag descriptions, read from repo profiles.

Global flags come from ``profiles/use.desc``; package-specific ones from
``profiles/use.local.desc`` (keyed ``cat/pkg:flag``). We read these once across
all configured repositories and cache them.
"""

from __future__ import annotations

import functools
import os

import portage


def _parse(path: str, into: dict[str, str]) -> None:
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or " - " not in line:
                    continue
                key, desc = line.split(" - ", 1)
                into.setdefault(key.strip(), desc.strip())
    except OSError:
        pass


@functools.lru_cache(maxsize=1)
def _global() -> dict[str, str]:
    d: dict[str, str] = {}
    for repo in portage.settings.repositories:
        _parse(os.path.join(repo.location, "profiles", "use.desc"), d)
    return d


@functools.lru_cache(maxsize=1)
def _local() -> dict[str, str]:
    d: dict[str, str] = {}
    for repo in portage.settings.repositories:
        _parse(os.path.join(repo.location, "profiles", "use.local.desc"), d)
    return d


def describe(cp: str, flag: str) -> str:
    """Best available description for ``flag`` on package ``cp`` ("" if none)."""
    return _local().get(f"{cp}:{flag}") or _global().get(flag, "")
