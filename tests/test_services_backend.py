"""Tests for the services backend argv builders."""

from gest.backend.services import ServicesService


def test_control_argv():
    assert ServicesService._control_argv("sshd", "start")[-2:] == ["sshd", "start"]


def test_enabled_argv():
    assert ServicesService._enabled_argv("sshd", True, "default")[-3:] == ["add", "sshd", "default"]
    assert ServicesService._enabled_argv("sshd", False, "boot")[-3:] == ["del", "sshd", "boot"]
    # unknown runlevel falls back to default
    assert ServicesService._enabled_argv("sshd", True, "bogus")[-1] == "default"
