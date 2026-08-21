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


# --- OpenRC argv builders ---------------------------------------------------

def test_control_argv_rc():
    argv = ServicesService._control_argv_rc
    assert argv("ollama", "start")[-2:] == ["ollama", "start"]
    assert argv("ollama", "restart")[-2:] == ["ollama", "restart"]


def test_enabled_argv_rc_adds_to_default_runlevel():
    argv = ServicesService._enabled_argv_rc("ollama", True)
    assert argv[-3:] == ["add", "ollama", "default"]


def test_enabled_argv_rc_del_has_no_runlevel():
    # `rc-update del <name>` (no runlevel) removes from every runlevel.
    argv = ServicesService._enabled_argv_rc("ollama", False)
    assert argv[-2:] == ["del", "ollama"]
