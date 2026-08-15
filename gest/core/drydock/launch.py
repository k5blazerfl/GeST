"""The Drydock launch pipeline — assemble the (env, argv) for a program.

Pure and unit-testable (the runtime — Wine/Proton/GPU — is the host-only part).
The argv is composed **outside-in**: ``gamemoderun`` → ``gamescope … --mangoapp
--`` → the runner (``umu-run`` | ``wine``) → ``<exe> <args>``. MangoHud is the
``--mangoapp`` flag under gamescope, else the ``MANGOHUD=1`` env — never both.
Proton bottles run through ``umu-run`` (which bundles DXVK/VKD3D and protonfixes).
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable

from gest.core.drydock.model import RUNNER_PROTON, Bottle, Program

UMU_RUN = "umu-run"
WINE = "wine"
GAMESCOPE = "gamescope"
GAMEMODERUN = "gamemoderun"

# (argv, env-overrides) -> exit code
Spawn = Callable[[list[str], dict], int]


def build_env(bottle: Bottle, program: Program) -> dict[str, str]:
    """The environment overrides for launching ``program`` (merged over the
    caller's environment at spawn time)."""
    env: dict[str, str] = dict(bottle.env)  # bottle-level overrides first
    graphics = program.graphics
    if bottle.prefix:
        env["WINEPREFIX"] = bottle.prefix

    if bottle.runner == RUNNER_PROTON:
        env["GAMEID"] = program.id or "umu-default"  # keys protonfixes
        env["STORE"] = "none"
        if bottle.runner_version:
            env["PROTONPATH"] = bottle.runner_version
    else:  # wine
        env["WINEARCH"] = bottle.arch
        env["WINEESYNC"] = "1" if graphics.esync else "0"
        env["WINEFSYNC"] = "1" if graphics.fsync else "0"

    if graphics.dxvk_hud:
        env["DXVK_HUD"] = graphics.dxvk_hud
    if graphics.fps_cap:
        env["DXVK_FRAME_RATE"] = str(graphics.fps_cap)
        env["VKD3D_FRAME_RATE"] = str(graphics.fps_cap)
    # MangoHud env only when NOT under gamescope (there it's the --mangoapp flag).
    if graphics.mangohud and not graphics.gamescope:
        env["MANGOHUD"] = "1"
    return env


def _runner_argv(bottle: Bottle, program: Program) -> list[str]:
    runner = UMU_RUN if bottle.runner == RUNNER_PROTON else WINE
    return [runner, program.exe, *program.args]


def _gamescope_argv(program: Program) -> list[str]:
    graphics = program.graphics
    argv = [GAMESCOPE]
    if graphics.gamescope_width and graphics.gamescope_height:
        argv += ["-W", str(graphics.gamescope_width), "-H", str(graphics.gamescope_height)]
    argv.append("-f")
    if graphics.fsr:
        argv += ["-F", "fsr"]
    if graphics.hdr:
        argv.append("--hdr-enabled")
    if graphics.mangohud:
        argv.append("--mangoapp")
    argv.append("--")
    return argv


def build_argv(bottle: Bottle, program: Program) -> list[str]:
    """The full wrapped command line for ``program``."""
    argv = _runner_argv(bottle, program)
    if program.graphics.gamescope:
        argv = _gamescope_argv(program) + argv
    if program.graphics.gamemode:
        argv = [GAMEMODERUN, *argv]
    return argv


def _default_spawn(argv: list[str], env: dict) -> int:
    return subprocess.run(argv, env={**os.environ, **env}).returncode


def launch(bottle: Bottle, program: Program, *, spawn: Spawn = _default_spawn) -> int:
    """Launch ``program`` from ``bottle``; returns the process exit code."""
    return spawn(build_argv(bottle, program), build_env(bottle, program))
