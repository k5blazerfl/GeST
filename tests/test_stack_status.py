"""Tests for packaging/stack-status.py — the release-stack drift detector.

Exercises the drift logic with synthetic fixtures (so it never depends on the
repo's current version state) plus one smoke gate that the detector reports the
real tree as coherent. Pure stdlib — runs in the dependency-light CI subset.
"""

import importlib.util
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent.parent / "packaging" / "stack-status.py"
_spec = importlib.util.spec_from_file_location("stack_status", _MOD_PATH)
ss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ss)


def test_semver_key_orders_numerically():
    assert ss._semver_key("0.53.2") == (0, 53, 2)
    assert ss._semver_key("0.9.0") < ss._semver_key("0.10.0")  # not lexical
    assert ss._newest({"0.52.9", "0.53.0", "0.5.0"}) == "0.53.0"
    assert ss._newest(set()) is None


def test_emerge_line_regex_distinguishes_source_and_binary():
    src = ">>> Emerging (12 of 40) app-admin/gest-0.53.2::gest"
    binp = ">>> Emerging binary (13 of 40) gui-apps/hede-0.3.0::amphitheater"
    m1 = ss._EMERGE_RE.match(src)
    assert m1 and m1.group("pkg") == "app-admin/gest" and not m1.group("bin")
    m2 = ss._EMERGE_RE.match(binp)
    assert m2 and m2.group("pkg") == "gui-apps/hede" and m2.group("bin")
    assert m2.group(3) == "0.3.0"


def test_iso_check_flags_binary_package():
    r = ss.Report()
    ss._iso_check(r, "hede", "0.3.5", ("0.3.0", True))   # reused a binpkg → the bug
    assert r.worst() == "FAIL"


def test_iso_check_flags_version_drift():
    r = ss.Report()
    ss._iso_check(r, "gest", "0.53.2", ("0.53.1", False))
    assert r.worst() == "FAIL"


def test_iso_check_ok_when_source_built_and_matching():
    r = ss.Report()
    ss._iso_check(r, "gest", "0.53.2", ("0.53.2", False))
    assert r.worst() == "OK"


def test_compare_reports_drift_match_and_missing():
    r = ss.Report()
    ss._compare(r, "hede", "Amphitheater", "0.3.5", "0.3.4")
    assert r.worst() == "FAIL"
    r2 = ss.Report()
    ss._compare(r2, "gest", "Amphitheater", "0.53.2", "0.53.2")
    assert r2.worst() == "OK"
    r3 = ss.Report()
    ss._compare(r3, "hede", "Amphitheater", "0.3.5", None)
    assert r3.worst() == "WARN"


def test_gather_flags_binpkg_fallback_from_a_build_log(tmp_path):
    log = tmp_path / "build.log"
    log.write_text(
        ">>> Emerging (12 of 40) app-admin/gest-0.53.2::gest\n"
        ">>> Emerging binary (13 of 40) gui-apps/hede-0.3.0::amphitheater\n",
        encoding="utf-8",
    )
    _facts, report = ss.gather(amphi=None, build_log=log)
    titles = [t for lvl, t, _ in report.checks if lvl == "FAIL"]
    assert any("BINARY package" in t for t in titles)


def test_gather_amphitheater_drift(tmp_path):
    (tmp_path / "app-admin" / "gest").mkdir(parents=True)
    (tmp_path / "gui-apps" / "hede").mkdir(parents=True)
    # a wildly-old hede ebuild → guaranteed drift vs the real source version
    (tmp_path / "gui-apps" / "hede" / "hede-0.0.1.ebuild").touch()
    _facts, report = ss.gather(amphi=tmp_path, build_log=None)
    assert any(lvl == "FAIL" and "Amphitheater drift" in t for lvl, t, _ in report.checks)


def test_real_tree_is_coherent_smoke():
    # The detector must report the checked-in tree as drift-free (non-strict:
    # an unreleased version bump is a WARN, not a FAIL). This is the CI gate.
    assert ss.main([]) == 0
