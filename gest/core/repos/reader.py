"""Read enabled Portage repositories from /etc/portage/repos.conf.

Parsing is the shared INI codec (:mod:`gest.core.portage.codec.ini`); this
module just merges the ``*.conf`` fragments and shapes them into :class:`Repo`
rows. Writes go through ``eselect repository`` (see ``core/repos/commands.py``),
never this module.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass

from gest.core.portage import paths
from gest.core.portage.codec import ini
from gest.core.repos import disabled as disabled_state
from gest.core.repos import refresh as refresh_state

REPOS_CONF = "/etc/portage/repos.conf"


@dataclass(slots=True)
class Repo:
    name: str
    sync_type: str = ""
    sync_uri: str = ""
    location: str = ""
    priority: str = ""
    auto_sync: str = ""
    main: bool = False
    refresh: bool = False   # sync this repo when Software Management opens
    enabled: bool = True    # False for repos GeST disabled (kept for re-adding)


def enabled_repos(conf_dir: str | None = None) -> list[Repo]:
    """Every configured repository, main repo first then alphabetical.

    Merges each ``*.conf`` fragment (later files win, matching Portage) and
    resolves ``main-repo`` from any fragment's ``[DEFAULT]`` block.
    """
    conf_dir = conf_dir or paths.repos_conf_dir()
    merged: dict[str, dict[str, str]] = {}
    main_repo = ""
    try:
        files = sorted(glob.glob(os.path.join(conf_dir, "*.conf")))
    except OSError:
        files = []
    for path in files:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        defaults, sections = ini.parse(text)
        if defaults.get("main-repo"):
            main_repo = defaults["main-repo"]
        for sect in sections:
            merged[sect.name] = sect.entries
    refresh_names = _refresh_names(conf_dir)
    repos = [
        Repo(
            name=name,
            sync_type=data.get("sync-type", ""),
            sync_uri=data.get("sync-uri", ""),
            location=data.get("location", ""),
            priority=data.get("priority", ""),
            auto_sync=data.get("auto-sync", ""),
            main=(name == main_repo),
            refresh=(name in refresh_names),
        )
        for name, data in merged.items()
    ]
    return sorted(repos, key=lambda r: (not r.main, r.name))


def _refresh_names(conf_dir: str) -> set[str]:
    """The set of repos flagged for refresh-on-open, read from GeST's state file.

    The state file is ``<etc/portage>/gest/refresh`` — a sibling of ``conf_dir``
    (``repos.conf``) — so it tracks whatever root ``conf_dir`` is under.
    """
    return _read_gest_state(conf_dir, refresh_state.STATE_NAME, refresh_state.parse,
                            default=set())


def disabled_repos(conf_dir: str | None = None) -> list[Repo]:
    """Repositories GeST has disabled, from ``<etc/portage>/gest/disabled``.

    Returned as :class:`Repo` rows with ``enabled=False`` and the saved sync
    info, so the screen can show them (greyed) and re-add them without retyping.
    """
    conf_dir = conf_dir or paths.repos_conf_dir()
    rows = _read_gest_state(conf_dir, disabled_state.STATE_NAME,
                            disabled_state.parse, default=[])
    return sorted(
        (Repo(name=d.name, sync_type=d.sync_type, sync_uri=d.sync_uri,
              priority=d.priority, enabled=False) for d in rows),
        key=lambda r: r.name)


def _read_gest_state(conf_dir: str, name: str, parse, default):
    """Read + parse a GeST state file that is a sibling of ``conf_dir``/../gest."""
    etc_portage = os.path.dirname(os.path.normpath(conf_dir))
    path = os.path.join(etc_portage, "gest", name)
    try:
        with open(path, encoding="utf-8") as fh:
            return parse(fh.read())
    except OSError:
        return default
