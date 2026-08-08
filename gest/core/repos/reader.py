"""Read enabled Portage repositories from /etc/portage/repos.conf."""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass

REPOS_CONF = "/etc/portage/repos.conf"


@dataclass(slots=True)
class Repo:
    name: str
    sync_type: str = ""
    sync_uri: str = ""
    location: str = ""
    main: bool = False


def parse_repos_conf(text: str) -> dict[str, dict[str, str]]:
    """Parse a repos.conf INI file into {section: {key: value}} (skips DEFAULT)."""
    result: dict[str, dict[str, str]] = {}
    main_repo = ""
    current: str | None = None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith(";"):
            continue
        if s.startswith("[") and s.endswith("]"):
            name = s[1:-1].strip()
            current = None if name.upper() == "DEFAULT" else name
            if current is not None:
                result.setdefault(current, {})
            else:
                current = "\0DEFAULT"  # capture DEFAULT keys separately
                result.setdefault(current, {})
            continue
        if current and "=" in line:
            key, _, value = line.partition("=")
            result[current][key.strip()] = value.strip()
    default = result.pop("\0DEFAULT", {})
    main_repo = default.get("main-repo", "")
    if main_repo:
        result.setdefault("\0main", {})["name"] = main_repo
    return result


def enabled_repos(conf_dir: str = REPOS_CONF) -> list[Repo]:
    merged: dict[str, dict[str, str]] = {}
    main_repo = ""
    try:
        files = sorted(glob.glob(os.path.join(conf_dir, "*.conf")))
    except OSError:
        files = []
    for path in files:
        try:
            with open(path, encoding="utf-8") as fh:
                parsed = parse_repos_conf(fh.read())
        except OSError:
            continue
        if "\0main" in parsed:
            main_repo = parsed.pop("\0main")["name"]
        merged.update(parsed)
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
