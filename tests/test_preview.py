"""Tests for the install-preview parsing and runner injection."""

from gest.core.software.preview import PreviewResult, preview_install


def test_summary_extracts_total_line():
    out = (
        "Calculating dependencies ... done!\n"
        "[ebuild  N     ] cat/pkg-1.0\n"
        "Total: 3 packages (3 new), Size of downloads: 10 KiB\n"
    )
    r = PreviewResult("cat/pkg", 0, out)
    assert r.ok
    assert r.summary == "Total: 3 packages (3 new), Size of downloads: 10 KiB"


def test_summary_reports_error_when_unresolved():
    out = '!!! There are no ebuilds to satisfy "cat/nope".'
    r = PreviewResult("cat/nope", 1, out)
    assert not r.ok
    assert "no ebuilds" in r.summary.lower()


def test_summary_fallback_when_ok_but_no_total():
    r = PreviewResult("cat/pkg", 0, "Nothing looks out of the ordinary.")
    assert r.summary == "nothing to do"


def test_preview_install_uses_injected_runner():
    seen = {}

    def runner(argv):
        seen["argv"] = argv
        return 0, "Total: 1 package (1 new), Size of downloads: 0 KiB"

    r = preview_install("www-client/firefox", runner=runner)
    assert "--pretend" in seen["argv"]
    assert "www-client/firefox" in seen["argv"]
    assert r.ok
    assert r.summary.startswith("Total:")


def test_preview_changed_use_adds_flag():
    seen = {}

    def runner(argv):
        seen["argv"] = argv
        return 0, "Total: 1 package (1 reinstall), Size of downloads: 0 KiB"

    preview_install("cat/pkg", changed_use=True, runner=runner)
    assert "--changed-use" in seen["argv"]
    assert "cat/pkg" == seen["argv"][-1]  # atom stays last


def test_preview_world_builds_update_argv():
    seen = {}

    def runner(argv):
        seen["argv"] = argv
        return 0, "Total: 12 packages (12 upgrades)"

    from gest.core.software.preview import preview_world
    r = preview_world(runner=runner)
    assert "-uDN" in seen["argv"]
    assert seen["argv"][-1] == "@world"
    assert r.atom == "@world"
