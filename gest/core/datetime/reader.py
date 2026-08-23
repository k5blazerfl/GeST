"""Read the system clock, timezone and NTP status (unprivileged)."""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable

from gest.core.datetime.model import ClockInfo
from gest.core.services import reader as services_reader
from gest.core.system.timezone import current_timezone

Runner = Callable[[list[str]], str]

# systemd unit names that provide NTP time sync, most common first.
_NTP_DAEMONS = ("systemd-timesyncd.service", "chronyd.service", "ntpd.service",
                "ntpsec.service", "openntpd.service")


def now_string(when: _dt.datetime | None = None) -> str:
    return (when or _dt.datetime.now()).strftime("%Y-%m-%d %H:%M:%S")


def clock_line(when: _dt.datetime | None = None, *, sep: str = "*") -> str:
    """Welcome-screen clock: live time first, date second, ``sep`` between them."""
    return (when or _dt.datetime.now()).strftime(f"%H:%M:%S {sep} %Y-%m-%d")


def detect_ntp(services) -> tuple[str, bool, bool]:
    """From a list of Service objects, find an NTP daemon and its state.

    Returns (name, running, enabled); name is "" when none is installed.
    """
    by_name = {s.name: s for s in services}
    for daemon in _NTP_DAEMONS:
        svc = by_name.get(daemon)
        if svc is not None:
            return svc.name, svc.running, svc.enabled
    return "", False, False


def clock_info(runner: Runner | None = None) -> ClockInfo:
    services = services_reader.list_services(runner)
    name, running, enabled = detect_ntp(services)
    return ClockInfo(
        local_time=now_string(),
        timezone=current_timezone(),
        ntp_daemon=name,
        ntp_running=running,
        ntp_enabled=enabled,
    )
