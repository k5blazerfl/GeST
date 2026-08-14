"""Tests for the Network module's pure validation (gest.qt.net)."""

from gest.qt.net import validate_static


def test_valid_static():
    assert validate_static("192.168.1.10/24", "192.168.1.1") == ""
    assert validate_static("10.0.0.2/8", "") == ""  # gateway optional


def test_bad_address():
    assert validate_static("192.168.1.10", "").startswith("Address")  # no CIDR
    assert validate_static("not-an-ip/24", "") != ""


def test_bad_gateway():
    assert validate_static("192.168.1.10/24", "999.1.1.1").startswith("Gateway")
