"""Tests for the Portage reader against the live system Portage DB.

These are integration tests: they exercise the real ``portage`` API on the host
they run on, so assertions stay about *shape* and invariants rather than exact
package sets.
"""

from gest.core.software import reader
from gest.core.software.model import Package, SearchResult, UseFlag


def test_list_installed_returns_packages():
    pkgs = reader.list_installed()
    assert pkgs, "expected at least one installed package on a Gentoo host"
    assert all(isinstance(p, Package) for p in pkgs)
    p = pkgs[0]
    assert "/" in p.cp
    assert p.installed is True


def test_counts_are_consistent():
    c = reader.counts()
    assert c["installed"] == len(reader.list_installed())
    assert 0 <= c["world"] <= c["installed"]


def test_use_flag_str_roundtrip():
    assert str(UseFlag("wayland", True)) == "+wayland"
    assert str(UseFlag("systemd", False)) == "-systemd"


def test_search_empty_term_is_empty():
    assert reader.search("") == []


def test_search_finds_portage_itself():
    hits = reader.search("sys-apps/portage")
    assert any(h.cp == "sys-apps/portage" for h in hits)
    hit = next(h for h in hits if h.cp == "sys-apps/portage")
    assert isinstance(hit, SearchResult)
    assert hit.installed  # portage is, definitionally, installed


def test_get_package_prefers_installed():
    pkg = reader.get_package("sys-apps/portage")
    assert pkg is not None
    assert pkg.cp == "sys-apps/portage"
    assert pkg.installed is True
    assert pkg.version


def test_get_package_unknown_is_none():
    assert reader.get_package("no-such-cat/no-such-pkg-xyz") is None
