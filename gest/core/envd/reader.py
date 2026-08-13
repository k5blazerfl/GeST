"""Read the GeST env.d drop-in (unprivileged)."""

from __future__ import annotations

from gest.core.envd import config


def read_dropin(path: str = config.ENVD_DROPIN) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def current_vars(path: str = config.ENVD_DROPIN) -> dict[str, str]:
    """The VAR=value pairs GeST currently manages in its drop-in."""
    return config.parse_conf(read_dropin(path))
