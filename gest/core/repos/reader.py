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

REPOS_CONF = "/etc/portage/repos.conf"


@dataclass(slots=True)
class Repo:
    name: str
    sync_type: str = ""
    sync_uri: str = ""
    location: str = ""
    main: bool = False


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
                defaults, sections = ini.parse(fh.read())
        except OSError:
            continue
        if defaults.get("main-repo"):
            main_repo = defaults["main-repo"]
        for sect in sections:
            merged[sect.name] = sect.entries
    repos = [
        Repo(
            name=name,
            sync_type=data.get("sync-type", ""),
            sync_uri=data.get("sync-uri", ""),
            location=data.get("location", ""),
            main=(name == main_repo),
        )
        for name, data in merged.items()
    ]
    return sorted(repos, key=lambda r: (not r.main, r.name))
