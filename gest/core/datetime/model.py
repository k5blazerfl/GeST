"""Data model for the date & time module."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ClockInfo:
    local_time: str = ""      # current local time, "YYYY-MM-DD HH:MM:SS"
    timezone: str = ""        # e.g. "America/New_York"
    ntp_daemon: str = ""      # OpenRC service name of a detected NTP daemon, or ""
    ntp_running: bool = False
    ntp_enabled: bool = False  # enabled at boot (systemctl is-enabled)

    @property
    def has_ntp(self) -> bool:
        return bool(self.ntp_daemon)
