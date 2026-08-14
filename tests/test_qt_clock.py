"""Tests for the Date & Time module's pure summary (gest.qt.clock)."""

from gest.core.datetime.model import ClockInfo
from gest.qt.clock import clock_summary


def test_summary_with_ntp():
    info = ClockInfo(
        local_time="2026-08-14 15:30:00",
        timezone="America/New_York",
        ntp_daemon="chronyd",
        ntp_running=True,
        ntp_enabled=True,
    )
    rows = dict(clock_summary(info))
    assert rows["Local time"] == "2026-08-14 15:30:00"
    assert rows["Timezone"] == "America/New_York"
    assert rows["NTP (chronyd)"] == "running, enabled at boot"


def test_summary_without_ntp():
    rows = dict(clock_summary(ClockInfo(local_time="", timezone="UTC")))
    assert rows["Local time"] == "—"
    assert rows["NTP"] == "not configured"
