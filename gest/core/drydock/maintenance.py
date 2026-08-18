"""Barrel maintenance: build the env+argv for the day-to-day Wine chores
(winetricks / winecfg / a prefix shell / kill), and probe which host tools are
installed. **Pure** builders — the CLI spawns them with an injectable runner, so
these are unit-testable without Wine.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable

from gest.core.drydock.model import Barrel


def barrel_env(barrel: Barrel) -> dict[str, str]:
    """``WINEPREFIX``/``WINEARCH`` (+ the barrel's env overrides) for a Wine
    maintenance command run against this barrel's prefix."""
    env = dict(barrel.env)
    if barrel.prefix:
        env["WINEPREFIX"] = barrel.prefix
    env["WINEARCH"] = barrel.arch
    return env


def winetricks_argv(verbs: list[str]) -> list[str]:
    return ["winetricks", *verbs]


def winecfg_argv() -> list[str]:
    return ["winecfg"]


def kill_argv() -> list[str]:
    """``wineserver -k`` — terminate every process in the barrel's prefix."""
    return ["wineserver", "-k"]


def shell_argv(shell: str) -> list[str]:
    """An interactive shell (``$SHELL``) with the barrel's Wine env exported, so
    the user can poke the prefix by hand."""
    return [shell or "bash"]


# The host tools each Drydock capability needs — `drydock doctor` reports them.
TOOLS: dict[str, str] = {
    "wine": "Wine — run apps, winecfg, wineserver",
    "winetricks": "winetricks — install DLLs/runtimes into a barrel",
    "wineserver": "wineserver — kill a barrel's processes",
    "umu-run": "umu-launcher — Proton barrels",
    "wrestool": "icoutils wrestool — extract .exe icons",
    "icotool": "icoutils icotool — convert extracted icons",
    "gamescope": "gamescope — game mode (FSR/HDR/scaling)",
    "gamemoderun": "gamemode — CPU/GPU performance mode",
    "mangohud": "MangoHud — performance overlay",
    "xdg-mime": "xdg-utils — register .exe/.rdp MIME handlers",
}


def probe_tools(which: Callable[[str], str | None] = shutil.which
                ) -> list[tuple[str, str | None, str]]:
    """``(tool, resolved-path-or-None, description)`` for each known host tool."""
    return [(tool, which(tool), desc) for tool, desc in TOOLS.items()]
