"""CI-safe tests for the sync parser (emerge --sync per-repo markers)."""

from gest.core.software import sync


def test_parse_sync_event_start():
    ev = sync.parse_sync_event(
        ">>> Syncing repository 'gentoo' into '/var/db/repos/gentoo'...")
    assert ev is not None
    assert ev.kind == "start" and ev.repo == "gentoo" and ev.code is None


def test_parse_sync_event_result():
    ok = sync.parse_sync_event("Action: sync for repo: gentoo, returned code = 0")
    assert (ok.kind, ok.repo, ok.code) == ("result", "gentoo", 0)
    fail = sync.parse_sync_event("Action: sync for repo: zGentoo, returned code = 1")
    assert fail.code == 1 and fail.repo == "zGentoo"


def test_parse_sync_event_ignores_noise():
    assert sync.parse_sync_event("receiving incremental file list") is None
    assert sync.parse_sync_event("Calculating dependencies ... done!") is None
