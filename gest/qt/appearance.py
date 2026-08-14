"""Qt-free helpers for the Appearance module (unit-testable without PySide).

The module drives HeDE's ``helm-theme`` writer (the single source of truth for
theme config); these helpers build its argv and read back the current choice
from hede.conf.
"""

from __future__ import annotations

import configparser
import os


def theme_args(dark: bool, accent: str = "", gtk: str = "", icon: str = "") -> list[str]:
    """Argv for ``helm-theme`` from an appearance choice."""
    args = ["--dark" if dark else "--light"]
    if accent:
        args.append(f"--accent={accent}")
    if gtk:
        args.append(f"--gtk-theme={gtk}")
    if icon:
        args.append(f"--icon-theme={icon}")
    return args


def default_config_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "hede", "hede.conf")


def read_appearance(path: str) -> tuple[bool, str]:
    """Current (dark, accent) from hede.conf's [appearance]; defaults if absent."""
    cp = configparser.ConfigParser()
    try:
        cp.read(path)
    except (OSError, configparser.Error):
        return (False, "")
    dark = cp.getboolean("appearance", "dark", fallback=False)
    accent = cp.get("appearance", "accent", fallback="")
    return (dark, accent)
