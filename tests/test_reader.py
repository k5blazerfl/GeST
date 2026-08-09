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


def test_get_package_detail_for_installed_package():
    # portage is always installed on a Gentoo host running these tests.
    detail = reader.get_package_detail("sys-apps/portage")
    assert detail is not None
    assert detail.cp == "sys-apps/portage"
    assert detail.installed_version  # it is installed
    assert detail.license            # LICENSE is populated
    assert reader.get_package_detail("no-such/package-xyz") is None


def test_search_summary_is_superset_of_name():
    name_only = reader.search("editor", fields=("name",))
    with_summary = reader.search("editor", fields=("name", "summary"), limit=500)
    names = {r.cp for r in name_only}
    both = {r.cp for r in with_summary}
    # summary search still matches every name hit, plus description-only hits
    assert names <= both
    assert len(both) >= len(names)


def test_list_categories_includes_known_categories():
    cats = reader.list_categories()
    assert "sys-apps" in cats and "dev-python" in cats
    assert cats == sorted(cats)  # returned sorted


def test_packages_in_category_are_scoped_and_sorted():
    pkgs = reader.packages_in_category("sys-apps")
    assert pkgs
    assert all(r.cp.startswith("sys-apps/") for r in pkgs)
    assert [r.cp for r in pkgs] == sorted(r.cp for r in pkgs)
    assert any(r.cp == "sys-apps/portage" for r in pkgs)
