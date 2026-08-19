"""Qt-free helpers for the Appearance module (unit-testable without PySide).

The module drives HeDE's ``helm-theme`` writer (the single source of truth for
theme config); these helpers build its argv and read back the current choice
from hede.conf.
"""

from __future__ import annotations

import configparser
import os
import re
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


# --- boot-splash sync (the session trigger for SyncBootTheme) ---

def read_boot_sync(path: str) -> bool:
    """Whether the boot splash should track the biome (hede.conf [boot]
    sync_with_biome). Default True — opt-out, not opt-in."""
    cp = configparser.ConfigParser()
    try:
        cp.read(path)
    except (OSError, configparser.Error):
        return True
    return cp.getboolean("boot", "sync_with_biome", fallback=True)


def set_boot_sync_text(existing: str, on: bool) -> str:
    """Return ``existing`` hede.conf text with ``[boot] sync_with_biome`` set to
    ``on``, inserting the key/section if absent and leaving the rest byte-for-byte
    (a surgical edit rather than a configparser rewrite, to stay clear of
    helm-theme's QSettings-written format)."""
    newline = f"sync_with_biome={'true' if on else 'false'}"
    lines = existing.splitlines()

    boot_start = next((i for i, r in enumerate(lines) if r.strip() == "[boot]"), None)
    if boot_start is None:  # no [boot] section → append one
        out = list(lines)
        if out and out[-1].strip():
            out.append("")
        out += ["[boot]", newline]
        return "\n".join(out) + "\n"

    boot_end = next((j for j in range(boot_start + 1, len(lines))
                     if lines[j].strip().startswith("[") and lines[j].strip().endswith("]")),
                    len(lines))
    for k in range(boot_start + 1, boot_end):  # replace an existing key in place
        if re.match(r"\s*sync_with_biome\s*=", lines[k]):
            return "\n".join(lines[:k] + [newline] + lines[k + 1:]) + "\n"
    # section present but key absent → insert right after the header
    return "\n".join(lines[:boot_start + 1] + [newline] + lines[boot_start + 1:]) + "\n"


def write_boot_sync(path: str, on: bool) -> None:
    """Persist the [boot] sync_with_biome toggle to hede.conf at ``path``."""
    try:
        with open(path, encoding="utf-8") as f:
            existing = f.read()
    except OSError:
        existing = ""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(set_boot_sync_text(existing, on))


def boot_sync_target(path: str) -> tuple[str, str]:
    """The (accent, world) to hand SyncBootTheme: the explicit [appearance]
    accent (may be "" → the backend derives it from the world) and the active
    [world] id (default "harbor")."""
    cp = configparser.ConfigParser()
    try:
        cp.read(path)
    except (OSError, configparser.Error):
        return ("", "harbor")
    accent = cp.get("appearance", "accent", fallback="")
    world = cp.get("world", "id", fallback="harbor")
    return (accent, world)
