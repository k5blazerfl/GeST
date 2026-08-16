"""CI-safe tests for the date & time core (pure validation + NTP detection)."""

import datetime as dt

import pytest

from gest.core.datetime import commands, reader
from gest.core.services.model import Service


def test_valid_datetime():
    assert commands.valid_datetime("2026-08-08 12:00:00")
    assert not commands.valid_datetime("2026-13-01 00:00:00")  # bad month
    assert not commands.valid_datetime("nope")
    assert not commands.valid_datetime("2026/08/08 12:00:00")  # wrong separators


def test_set_clock_argv_builds_and_rejects():
    assert commands.set_clock_argv("2026-08-08 12:00:00") == \
        ["date", "-s", "2026-08-08 12:00:00"]
    for bad in ("bad", "2026/08/08", "2026-08-08 12:00:00; rm -rf /"):
        with pytest.raises(ValueError):
            commands.set_clock_argv(bad)


def test_detect_ntp_prefers_known_daemon():
    svcs = [Service("sshd.service", "active", enabled_state="enabled"),
            Service("chronyd.service", "active", enabled_state="enabled")]
    assert reader.detect_ntp(svcs) == ("chronyd.service", True, True)


def test_detect_ntp_reports_stopped_disabled():
    svcs = [Service("openntpd.service", "inactive", enabled_state="disabled")]
    assert reader.detect_ntp(svcs) == ("openntpd.service", False, False)


def test_detect_ntp_none_installed():
    assert reader.detect_ntp(
        [Service("sshd.service", "active", enabled_state="enabled")]
    ) == ("", False, False)


def test_now_string_format():
    assert reader.now_string(dt.datetime(2026, 8, 8, 12, 0, 0)) == "2026-08-08 12:00:00"
