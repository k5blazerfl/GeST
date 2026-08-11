"""Pure tests for the user-preferences store (no XDG, no real config touched)."""

import pytest

from gest.core import prefs


def test_default_is_timer(tmp_path):
    assert prefs.accept_mode(str(tmp_path / "prefs.ini")) == prefs.TIMER


def test_roundtrip_each_mode(tmp_path):
    p = str(tmp_path / "prefs.ini")
    for mode in prefs.ACCEPT_MODES:
        prefs.set_accept_mode(mode, p)
        assert prefs.accept_mode(p) == mode


def test_set_creates_missing_dirs(tmp_path):
    p = str(tmp_path / "nested" / "gest" / "prefs.ini")
    prefs.set_accept_mode(prefs.IMMEDIATE, p)
    assert prefs.accept_mode(p) == prefs.IMMEDIATE


def test_invalid_mode_rejected(tmp_path):
    with pytest.raises(ValueError):
        prefs.set_accept_mode("bogus", str(tmp_path / "prefs.ini"))


def test_corrupt_file_falls_back_to_default(tmp_path):
    p = tmp_path / "prefs.ini"
    p.write_text("this is not ini @@@\n")           # no section header
    assert prefs.accept_mode(str(p)) == prefs.TIMER


def test_unknown_stored_value_falls_back_to_default(tmp_path):
    p = tmp_path / "prefs.ini"
    p.write_text("[ui]\naccept_mode = bogus\n")
    assert prefs.accept_mode(str(p)) == prefs.TIMER
