"""Detect the installed escalation tools and read the current GeST policy.

Which tools exist and what GeST has already written are unprivileged reads
(``/etc/sudoers.d`` is root-only readable, so the sudo policy read is best-effort
and the backend remains the source of truth for a privileged view).
"""

from __future__ import annotations

import shutil

from gest.core.privilege import render
from gest.core.privilege.model import DOAS_CONF, SUDOERS_DROPIN, EscalationPolicy


def available_tools() -> list[str]:
    """Whichever of sudo/doas are installed, in preference order."""
    return [tool for tool in ("doas", "sudo") if shutil.which(tool)]


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def sudo_policy(path: str = SUDOERS_DROPIN) -> EscalationPolicy | None:
    """The GeST sudo drop-in policy, or ``None`` if it isn't present/readable."""
    return render.parse_sudoers(_read(path))


def doas_policy(path: str = DOAS_CONF) -> EscalationPolicy | None:
    """The GeST-managed doas policy block, or ``None`` if absent."""
    return render.parse_doas_block(_read(path))
