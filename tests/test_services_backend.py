"""Tests for the services backend argv builders (systemd)."""

from gest.backend.services import ServicesService


def test_control_argv():
    argv = ServicesService._control_argv
    assert argv("sshd.service", "start")[-2:] == ["start", "sshd.service"]
    assert argv("sshd.service", "restart")[-2:] == ["restart", "sshd.service"]


def test_enabled_argv():
    assert ServicesService._enabled_argv("sshd.service", True)[-2:] == ["enable", "sshd.service"]
    assert ServicesService._enabled_argv("sshd.service", False)[-2:] == ["disable", "sshd.service"]


def test_masked_argv():
    assert ServicesService._masked_argv("sshd.service", True)[-2:] == ["mask", "sshd.service"]
    assert ServicesService._masked_argv("sshd.service", False)[-2:] == ["unmask", "sshd.service"]
