"""Read/list/validate the system timezone (zoneinfo)."""

from __future__ import annotations

import os
import re

_ZONE_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_+-]*(/[A-Za-z0-9][A-Za-z0-9_+-]*)*\Z")
# zoneinfo subdirs that aren't user-facing zones
_SKIP = {"posix", "right"}


def valid_zone_name(zone: str) -> bool:
    return bool(_ZONE_RE.match(zone)) and ".." not in zone


def list_zones(root: str = "/usr/share/zoneinfo") -> list[str]:
    """Every timezone under ``root`` (e.g. 'America/New_York'), sorted."""
    zones: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        top = rel.split(os.sep, 1)[0]
        if top in _SKIP:
            dirnames[:] = []
            continue
        for name in filenames:
            full = os.path.join(dirpath, name)
            zone = os.path.relpath(full, root)
            # zones are Title-cased regions; skip lowercase data files (tzdata,
            # iso3166.tab, etc.) and anything with an extension.
            if "." in name or not name[:1].isupper():
                continue
            if valid_zone_name(zone):
                zones.append(zone)
    return sorted(set(zones))


def current_timezone(
    path: str = "/etc/timezone",
    *,
    localtime: str = "/etc/localtime",
    zoneinfo: str = "/usr/share/zoneinfo",
) -> str:
    """Current timezone name.

    Prefers ``/etc/timezone`` (Gentoo's canonical file); falls back to resolving
    the ``/etc/localtime`` symlink into a zoneinfo-relative name for systems that
    only have the symlink.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            line = fh.read().strip().splitlines()[0].strip()
        if line:
            return line
    except (OSError, IndexError):
        pass
    try:
        target = os.path.realpath(localtime)
        root = os.path.realpath(zoneinfo)
        if target.startswith(root + os.sep):
            zone = os.path.relpath(target, root)
            if valid_zone_name(zone):
                return zone
    except OSError:
        pass
    return ""
