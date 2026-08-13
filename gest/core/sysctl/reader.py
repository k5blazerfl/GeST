"""Read the GeST sysctl drop-in and live kernel values (unprivileged)."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from gest.core.sysctl import config
from gest.core.sysctl.commands import sysctl_read_argv

Runner = Callable[[list[str]], str]


def read_dropin(path: str = config.SYSCTL_DROPIN) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def current_settings(path: str = config.SYSCTL_DROPIN) -> dict[str, str]:
    """The key=value settings GeST currently manages in its drop-in."""
    return config.parse_conf(read_dropin(path))


def _default_runner(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True).stdout
    except OSError:
        return ""


def live_value(key: str, runner: Runner | None = None) -> str:
    """The current in-kernel value of ``key`` (`sysctl -n`), or "" if unreadable."""
    if not config.valid_key(key):
        return ""
    run = runner or _default_runner
    return run(sysctl_read_argv(key)).strip()
