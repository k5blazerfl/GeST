"""Tests for gest.core.portage.mirrors — the mirror catalog, latency ranking,
auto-select with offline fallback, and the GENTOO_MIRRORS / repos.conf renderers.
Hermetic: the network probe is injected (no real sockets)."""

from gest.core.portage.mirrors import (
    CATALOG,
    Mirror,
    MirrorSelection,
    default_selection,
    gentoo_repos_conf,
    probe_latency,
    rank_mirrors,
    render_gentoo_mirrors,
    select_mirrors,
)

_CAT = (
    Mirror("fast", "us-east", "https://fast.example/gentoo/", "rsync://fast.example/x"),
    Mirror("slow", "eu", "https://slow.example/gentoo/", "rsync://slow.example/x"),
    Mirror("dead", "asia", "https://dead.example/gentoo/", "rsync://dead.example/x"),
)


def _probe(latencies):
    def probe(uri, *, timeout=2.0):
        return latencies.get(uri)
    return probe


# --- ranking ---------------------------------------------------------------

def test_rank_orders_by_latency_and_drops_unreachable():
    probe = _probe({"https://fast.example/gentoo/": 0.01,
                    "https://slow.example/gentoo/": 0.5})   # dead → None
    ranked = rank_mirrors(_CAT, probe=probe, top=3)
    assert [m.name for m in ranked] == ["fast", "slow"]     # dead dropped, fast first


def test_rank_respects_top():
    probe = _probe({"https://fast.example/gentoo/": 0.01,
                    "https://slow.example/gentoo/": 0.5,
                    "https://dead.example/gentoo/": 0.9})
    assert [m.name for m in rank_mirrors(_CAT, probe=probe, top=1)] == ["fast"]


# --- select + fallback -----------------------------------------------------

def test_select_uses_probe_when_reachable():
    probe = _probe({"https://fast.example/gentoo/": 0.01,
                    "https://slow.example/gentoo/": 0.5})
    sel = select_mirrors(catalog=_CAT, probe=probe, top=2)
    assert sel.probed is True and sel.ok
    assert sel.distfiles == ("https://fast.example/gentoo/", "https://slow.example/gentoo/")
    assert sel.sync_uri == "rsync://fast.example/x"


def test_select_falls_back_to_regional_default_when_offline():
    sel = select_mirrors(catalog=_CAT, probe=lambda *a, **k: None, region="us-east")
    assert sel.probed is False and sel.ok
    assert sel.distfiles == ("https://fast.example/gentoo/",)   # the us-east entry
    assert sel.sync_uri == "rsync://fast.example/x"


def test_default_selection_uses_whole_catalog_when_region_absent():
    sel = default_selection(catalog=_CAT, region="antarctica", top=2)
    assert sel.probed is False
    assert sel.distfiles == ("https://fast.example/gentoo/", "https://slow.example/gentoo/")


# --- renderers -------------------------------------------------------------

def test_render_gentoo_mirrors_from_selection_and_list():
    sel = MirrorSelection(distfiles=("https://a/", "https://b/"), sync_uri="rsync://a/x")
    assert render_gentoo_mirrors(sel) == "https://a/ https://b/"
    assert render_gentoo_mirrors(["https://c/"]) == "https://c/"


def test_gentoo_repos_conf_has_sync_uri_and_autosync():
    conf = gentoo_repos_conf("rsync://rsync.us.gentoo.org/gentoo-portage")
    assert "[gentoo]" in conf
    assert "location = /var/db/repos/gentoo" in conf
    assert "sync-uri = rsync://rsync.us.gentoo.org/gentoo-portage" in conf
    assert "auto-sync = yes" in conf


def test_mirror_selection_ok_flag():
    assert MirrorSelection(distfiles=("https://a/",), sync_uri="rsync://a/x").ok
    assert not MirrorSelection(distfiles=(), sync_uri="").ok


# --- probe host parsing ----------------------------------------------------

def test_probe_latency_returns_none_for_a_uri_without_host():
    assert probe_latency("not-a-url", timeout=0.01) is None


def test_catalog_entries_are_well_formed():
    # every shipped entry has an https distfiles URL and an rsync sync-uri
    assert CATALOG
    for m in CATALOG:
        assert m.distfiles.startswith("https://")
        assert m.rsync.startswith("rsync://")
        assert m.region in {"us-east", "us-west", "eu", "asia", "oceania", "global"}
