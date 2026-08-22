"""CI-safe tests for the pure logic of the Gangway Phase-5b RAIL feasibility
spike harness (``scripts/host-validation/rail-spike.py``). The spike itself is
host-validated (needs a real Windows VM + FreeRDP + an X server); only its
argv-building, xprop parsing, and verdict math are exercised here.

The harness lives under ``scripts/`` (not shipped in the wheel), so it is loaded
by file path rather than imported as a package module."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPIKE = Path(__file__).resolve().parent.parent / "scripts" / "host-validation" / "rail-spike.py"


def _load():
    spec = importlib.util.spec_from_file_location("rail_spike", _SPIKE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses (3.14) resolve __module__ via sys.modules
    spec.loader.exec_module(mod)
    return mod


rs = _load()


# ---- probe argv --------------------------------------------------------
def test_build_probe_argv_is_a_rail_launch():
    argv = rs.build_probe_argv("xfreerdp3", "10.0.0.9", "flotilla", "notepad")
    assert argv[0] == "xfreerdp3"
    assert "/v:10.0.0.9:3389" in argv
    assert "/u:flotilla" in argv
    assert "/app:program:notepad" in argv  # RAIL, by TSAppAllowList alias
    assert "/sec:nla" in argv and "/cert:tofu" in argv
    # no desktop-surface flags — we measure RAIL, not a full screen.
    assert "/f" not in argv and not any(a.startswith("/size:") for a in argv)


def test_build_probe_argv_password_is_never_on_argv():
    argv = rs.build_probe_argv("xfreerdp3", "h", "u", "app")
    assert "/from-stdin" in argv  # fed over stdin instead
    assert not any("/p:" in a or "password" in a.lower() for a in argv)


def test_build_probe_argv_custom_port_and_extra():
    argv = rs.build_probe_argv("xfreerdp3", "h", "u", "app", port=13389,
                               extra=["/log-level:trace"], from_stdin=False)
    assert "/v:h:13389" in argv
    assert "/log-level:trace" in argv
    assert "/from-stdin" not in argv


# ---- version gating (#12391 fixed in 3.24.0) ---------------------------
def test_parse_version():
    assert rs.parse_version("This is FreeRDP version 3.24.0 (release)") == (3, 24, 0)
    assert rs.parse_version("xfreerdp 3.5.1\n") == (3, 5, 1)
    assert rs.parse_version("no version here") is None


def test_version_ok_thresholds():
    assert rs.version_ok((3, 24, 0)) is True   # the fix release
    assert rs.version_ok((3, 25, 2)) is True
    assert rs.version_ok((3, 23, 0)) is False  # the broken release
    assert rs.version_ok((3, 22, 0)) is False  # pre-regression, but below our pin
    assert rs.version_ok(None) is False


# ---- xprop parsing -----------------------------------------------------
def test_parse_client_list():
    out = "_NET_CLIENT_LIST(WINDOW): window id # 0x1a00007, 0x1c00003, 0x2000005\n"
    assert rs.parse_client_list(out) == ["0x1a00007", "0x1c00003", "0x2000005"]


def test_parse_client_list_empty_or_absent():
    assert rs.parse_client_list("") == []
    assert rs.parse_client_list("_NET_CLIENT_LIST(WINDOW): window id # \n") == []
    # a different atom must not be misread as the client list.
    assert rs.parse_client_list("_NET_ACTIVE_WINDOW(WINDOW): 0x1a00007") == []


def test_parse_wm_class():
    assert rs.parse_wm_class('WM_CLASS(STRING) = "notepad", "Notepad"') == ("notepad", "Notepad")
    assert rs.parse_wm_class("WM_CLASS:  not found.") == ("", "")


# ---- verdict math ------------------------------------------------------
def _runs(*classes) -> list:
    """Build RunResults: a string → an appeared window with that WM_CLASS; None →
    no window."""
    out = []
    for c in classes:
        out.append(rs.RunResult(appeared=False) if c is None
                   else rs.RunResult(appeared=True, wm_class=c))
    return out


def test_app_passes_when_every_run_shows_one_stable_class():
    v = rs.AppVerdict(app_key="notepad", runs=_runs("Notepad", "Notepad", "Notepad"))
    assert v.all_appeared and v.stable_class and v.passed
    assert v.classes == {"Notepad"}


def test_app_fails_on_a_missing_window():
    # the #12391 / #12397 failure mode: works some runs, vanishes on another.
    v = rs.AppVerdict(app_key="notepad", runs=_runs("Notepad", None, "Notepad"))
    assert not v.all_appeared and not v.passed


def test_app_fails_on_unstable_class():
    v = rs.AppVerdict(app_key="notepad", runs=_runs("Notepad", "FreeRDP"))
    assert v.all_appeared and not v.stable_class and not v.passed


def test_app_fails_when_class_is_blank():
    v = rs.AppVerdict(app_key="x", runs=[rs.RunResult(appeared=True, wm_class="")])
    assert v.all_appeared and not v.stable_class  # a window with no identity is unusable


def test_evaluate_is_green_only_when_all_apps_pass():
    good = rs.AppVerdict("a", _runs("A", "A"))
    bad = rs.AppVerdict("b", _runs("B", None))
    assert rs.evaluate([good]) is True
    assert rs.evaluate([good, bad]) is False
    assert rs.evaluate([]) is False  # nothing probed is not a pass


def test_summarize_reports_verdict_and_classes():
    txt = rs.summarize([rs.AppVerdict("notepad", _runs("Notepad", "Notepad"))])
    assert "GREEN" in txt and "notepad" in txt and "Notepad" in txt
    red = rs.summarize([rs.AppVerdict("notepad", _runs("Notepad", None))])
    assert "RED" in red


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
