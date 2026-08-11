"""User-level GeST preferences (per-user, unprivileged).

These are frontend preferences — how the UI behaves — not system state, so they
live in the user's config dir ($XDG_CONFIG_HOME/gest/prefs.ini, default
~/.config/gest) and need no backend or root. The store is a tiny INI file; the
accessors validate on the way in and out so a hand-edited or stale file can
never feed an unknown value back into the UI.

Currently just the *accept mode* — how the install/remove review is confirmed:

    manual     review, then press F10/Enter to apply (no timer)
    timer      auto-apply after a short countdown (Esc stops, Enter applies now)
    immediate  apply the moment the plan resolves (no confirmation step)
"""

from __future__ import annotations

import configparser
import contextlib
import os

MANUAL = "manual"
TIMER = "timer"
IMMEDIATE = "immediate"
ACCEPT_MODES = (MANUAL, TIMER, IMMEDIATE)
_DEFAULT_MODE = TIMER

# Countdown length (seconds) for the ``timer`` mode, and its allowed range.
TIMER_MIN = 1
TIMER_MAX = 30
_DEFAULT_TIMER = 5

# Human label + one-line description per mode, in display order.
ACCEPT_LABELS: dict[str, tuple[str, str]] = {
    MANUAL: ("Click to accept",
             "Review, then press F10 / Enter to apply. No timer."),
    TIMER: ("Countdown timer",
            "Auto-apply after a few seconds — Esc stops it, Enter applies now."),
    IMMEDIATE: ("As soon as ready",
                "Apply the moment the plan resolves. No confirmation step."),
}


def _prefs_path(path: str | None = None) -> str:
    if path is not None:
        return path
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "gest", "prefs.ini")


def _read(path: str | None) -> configparser.ConfigParser:
    cp = configparser.ConfigParser()
    with contextlib.suppress(OSError, configparser.Error):
        cp.read(_prefs_path(path))              # missing/corrupt → defaults
    return cp


def _write(key: str, value: str, path: str | None) -> None:
    target = _prefs_path(path)
    cp = _read(path)
    if not cp.has_section("ui"):
        cp.add_section("ui")
    cp.set("ui", key, value)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        cp.write(fh)


def accept_mode(path: str | None = None) -> str:
    """The configured accept mode, or the default if unset/invalid."""
    mode = _read(path).get("ui", "accept_mode", fallback=_DEFAULT_MODE)
    return mode if mode in ACCEPT_MODES else _DEFAULT_MODE


def set_accept_mode(mode: str, path: str | None = None) -> None:
    """Persist the accept mode. Raises :class:`ValueError` on an unknown mode."""
    if mode not in ACCEPT_MODES:
        raise ValueError(f"invalid accept mode: {mode!r}")
    _write("accept_mode", mode, path)


def timer_seconds(path: str | None = None) -> int:
    """The countdown length for ``timer`` mode, clamped to the allowed range."""
    raw = _read(path).get("ui", "timer_seconds", fallback=str(_DEFAULT_TIMER))
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_TIMER                   # non-numeric → default
    return min(max(val, TIMER_MIN), TIMER_MAX)


def set_timer_seconds(seconds: int, path: str | None = None) -> None:
    """Persist the countdown length. Raises :class:`ValueError` out of range."""
    seconds = int(seconds)
    if not TIMER_MIN <= seconds <= TIMER_MAX:
        raise ValueError(f"timer seconds out of range [{TIMER_MIN}, {TIMER_MAX}]: "
                         f"{seconds}")
    _write("timer_seconds", str(seconds), path)
