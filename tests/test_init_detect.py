"""Tests for init-system detection (env override + filesystem probe)."""

import gest.core.init as init


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("GEST_INIT", "openrc")
    assert init.detect() == "openrc" and init.is_openrc() and not init.is_systemd()
    monkeypatch.setenv("GEST_INIT", "systemd")
    assert init.detect() == "systemd" and init.is_systemd() and not init.is_openrc()


def test_env_override_case_and_whitespace(monkeypatch):
    monkeypatch.setenv("GEST_INIT", "  OpenRC  ")
    assert init.detect() == "openrc"


def test_bad_override_falls_through_to_probe(monkeypatch):
    monkeypatch.setenv("GEST_INIT", "sysvinit")  # not a recognized value
    monkeypatch.setattr(init.os.path, "isdir",
                        lambda p: p == init._OPENRC_MARKER)
    assert init.detect() == "openrc"


def test_probe_prefers_systemd_marker(monkeypatch):
    monkeypatch.delenv("GEST_INIT", raising=False)
    monkeypatch.setattr(init.os.path, "isdir", lambda p: True)  # both present
    assert init.detect() == "systemd"


def test_probe_openrc_when_only_openrc_marker(monkeypatch):
    monkeypatch.delenv("GEST_INIT", raising=False)
    monkeypatch.setattr(init.os.path, "isdir",
                        lambda p: p == init._OPENRC_MARKER)
    assert init.detect() == "openrc"


def test_probe_defaults_to_systemd_when_no_marker(monkeypatch):
    monkeypatch.delenv("GEST_INIT", raising=False)
    monkeypatch.setattr(init.os.path, "isdir", lambda p: False)
    assert init.detect() == "systemd"
