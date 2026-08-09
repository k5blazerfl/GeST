"""Read the defaults applied to newly-created users (unprivileged).

Mirrors what ``useradd -D`` and ``/etc/login.defs`` drive: the default primary
group, home-directory prefix, login shell, account-inactivity and expiry
defaults, the skeleton directory, and the home-directory umask. Read-only —
GeST does not yet write these.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

USERADD_DEFAULTS = "/etc/default/useradd"
LOGIN_DEFS = "/etc/login.defs"


@dataclass(slots=True)
class NewUserDefaults:
    group: str = ""       # /etc/default/useradd GROUP (gid or name)
    home: str = ""        # HOME — path prefix for new home directories
    shell: str = ""       # SHELL
    inactive: str = ""    # INACTIVE — days after expiry the login still works
    expire: str = ""      # EXPIRE — default account expiration date
    skel: str = ""        # SKEL — skeleton directory
    umask: str = ""       # login.defs UMASK — mask for the new home directory


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def parse_kv(text: str) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines (``/etc/default/useradd`` style)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, value = s.partition("=")
        out[key.strip()] = value.strip()
    return out


def parse_login_defs(text: str) -> dict[str, str]:
    """Parse ``KEY   VALUE`` lines (whitespace-separated, ``login.defs`` style)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split(None, 1)
        if len(parts) == 2:
            out[parts[0]] = parts[1].strip()
    return out


def useradd_readable(path: str = USERADD_DEFAULTS) -> bool:
    """Whether the current (unprivileged) process can read useradd's defaults.

    ``/etc/default/useradd`` is commonly mode 0600, so an unprivileged TUI sees
    nothing there — worth distinguishing from "unset" in the UI.
    """
    return os.access(path, os.R_OK)


def read_defaults(useradd_path: str = USERADD_DEFAULTS,
                  login_defs_path: str = LOGIN_DEFS) -> NewUserDefaults:
    ua = parse_kv(_read(useradd_path))
    ld = parse_login_defs(_read(login_defs_path))
    return NewUserDefaults(
        group=ua.get("GROUP", ""),
        home=ua.get("HOME", ""),
        shell=ua.get("SHELL", ""),
        inactive=ua.get("INACTIVE", ""),
        expire=ua.get("EXPIRE", ""),
        skel=ua.get("SKEL", ""),
        umask=ld.get("UMASK", ""),
    )
