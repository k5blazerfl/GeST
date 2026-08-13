"""Read the current sshd_config settings (unprivileged).

sshd_config is world-readable, so parsing the managed directives needs no
privilege; validating and writing a change happen in the backend.
"""

from __future__ import annotations

from gest.core.sshd import config
from gest.core.sshd.model import SshdSettings

SSHD_CONFIG = "/etc/ssh/sshd_config"


def read_config(path: str = SSHD_CONFIG) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def current_settings(path: str = SSHD_CONFIG) -> SshdSettings:
    """The managed directives currently in ``path`` (OpenSSH defaults if absent)."""
    return config.parse_settings(read_config(path))
