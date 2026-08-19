"""Qt-free helpers for the Appearance module (unit-testable without PySide).

The module drives HeDE's ``helm-theme`` writer (the single source of truth for
theme config); these helpers build its argv and read back the current choice
from hede.conf.
"""

from __future__ import annotations

import configparser
import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class World:
    """A HeDE biome as reported by ``helm-theme --list-worlds``."""

    id: str
    name: str
    accent: str = ""
    wallpaper: str = ""


def parse_worlds(output: str) -> list[World]:
    """Parse ``helm-theme --list-worlds`` stdout (tab-separated id/name/accent/
    wallpaper per line). Missing trailing fields default to empty; a blank id
    line is skipped."""
    worlds: list[World] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        wid = parts[0].strip()
        if not wid:
            continue
        name = (parts[1].strip() if len(parts) > 1 else "") or wid
        accent = parts[2].strip() if len(parts) > 2 else ""
        wallpaper = parts[3].strip() if len(parts) > 3 else ""
        worlds.append(World(wid, name, accent, wallpaper))
    return worlds


def list_worlds() -> list[World]:
    """Installed worlds via ``helm-theme --list-worlds``; [] if HeDE is absent."""
    try:
        result = subprocess.run(
            ["helm-theme", "--list-worlds"], capture_output=True, text=True, check=False
        )
    except (FileNotFoundError, OSError):
        return []
    if result.returncode != 0:
        return []
    return parse_worlds(result.stdout)


def world_args(world_id: str) -> list[str]:
    """Argv for ``helm-theme`` to switch to a world."""
    return [f"--world={world_id}"]


def read_world(path: str) -> str:
    """The active world id from hede.conf's [world]; 'harbor' if unset/absent."""
    cp = configparser.ConfigParser()
    try:
        cp.read(path)
    except (OSError, configparser.Error):
        return "harbor"
    return cp.get("world", "id", fallback="harbor")


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
