"""Tests for the backend idle-exit decision."""

from gest.backend.service import SoftwareService


def test_should_exit_only_when_idle_and_no_active_ops():
    assert SoftwareService._should_exit(0, 130, 120) is True
    assert SoftwareService._should_exit(0, 119, 120) is False   # not idle enough
    assert SoftwareService._should_exit(1, 130, 120) is False   # merge streaming
    assert SoftwareService._should_exit(3, 999, 120) is False
