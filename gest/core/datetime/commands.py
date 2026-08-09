"""Pure, validated argv builder for setting the system clock."""

from __future__ import annotations

import datetime as _dt

_FORMAT = "%Y-%m-%d %H:%M:%S"


def valid_datetime(text: str) -> bool:
    """True if ``text`` is a well-formed 'YYYY-MM-DD HH:MM:SS' timestamp."""
    try:
        _dt.datetime.strptime(text.strip(), _FORMAT)
    except (ValueError, TypeError):
        return False
    return True


def set_clock_argv(text: str, *, date: str = "date") -> list[str]:
    """`date -s "YYYY-MM-DD HH:MM:SS"` — the timestamp is validated first."""
    text = text.strip()
    if not valid_datetime(text):
        raise ValueError(f"invalid timestamp: {text!r} (need YYYY-MM-DD HH:MM:SS)")
    return [date, "-s", text]
