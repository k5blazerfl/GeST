"""Audit logging for privileged backend actions.

Every mutation the root service performs is logged to the system log (authpriv)
with the calling user's uid, the action, and the outcome — so there is a record
of who changed what. ``format_audit`` is pure so it can be unit-tested; ``audit``
does the syslog emit.
"""

from __future__ import annotations

import syslog

_IDENT = "gest-backend"


def format_audit(action: str, uid: int | None, result: str, detail: str = "") -> str:
    who = f"uid={uid}" if uid is not None else "uid=?"
    parts = [who, f"action={action}", f"result={result}"]
    if detail:
        parts.append(f"detail={detail}")
    return " ".join(parts)


def audit(action: str, *, uid: int | None = None, result: str = "ok", detail: str = "") -> str:
    """Log a privileged action to authpriv; returns the formatted message."""
    message = format_audit(action, uid, result, detail)
    try:
        syslog.openlog(_IDENT, syslog.LOG_PID, syslog.LOG_AUTHPRIV)
        syslog.syslog(syslog.LOG_NOTICE, message)
    except Exception:  # logging must never break the operation
        pass
    return message
