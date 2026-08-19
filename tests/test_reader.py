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


def test_list_upgradable_is_a_subset_of_installed():
    installed = reader.list_installed()
    upgradable = reader.list_upgradable()
    inst_cps = {p.cp for p in installed}
    # every upgradable package is installed, carries a newer version string, and
    # reports upgradable=True
    for p in upgradable:
        assert p.cp in inst_cps
        assert p.installed
        assert p.available_version
        assert p.upgradable
    # list_upgradable is exactly the upgradable slice of list_installed
    assert {p.cp for p in upgradable} == {p.cp for p in installed if p.upgradable}


def test_upgradable_requires_installed_and_available_version():
    from gest.core.software.model import Package

    assert not Package(cp="x/y", version="1", available_version="2").upgradable  # not installed
    assert not Package(cp="x/y", version="1", installed=True).upgradable  # no newer version
    assert Package(cp="x/y", version="1", installed=True, available_version="2").upgradable


def test_list_unavailable_invariants():
    # Repo-orphans: installed cp's with no ebuild in any repo. We can't assume the
    # host has any, so assert the invariants that must hold for every row returned.
    rows = reader.list_unavailable()
    cps = [cp for cp, _ver, _w in rows]
    assert cps == sorted(cps)                      # sorted by cp
    installed_cps = {p.cp for p in reader.list_installed()}
    for cp, ver, world_member in rows:
        assert cp in installed_cps                 # it is actually installed
        assert ver                                 # carries the installed version
        assert isinstance(world_member, bool)
        assert not reader._PORTDB.cp_list(cp)      # truly has no ebuild anywhere


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


def test_search_exact_mode_matches_package_name():
    hits = reader.search("portage", fields=("name",), mode="exact")
    cps = {r.cp for r in hits}
    assert "sys-apps/portage" in cps          # pn == "portage"
    assert all(r.cp.split("/")[-1] == "portage" or r.cp == "portage" for r in hits)


def test_search_regexp_mode():
    hits = reader.search(r"^sys-apps/portage$", fields=("name",), mode="regexp")
    assert [r.cp for r in hits] == ["sys-apps/portage"]
    # an invalid regexp yields no results rather than raising
    assert reader.search("*bad(", fields=("name",), mode="regexp") == []


def test_search_ignore_case_toggle():
    insensitive = reader.search("PORTAGE", fields=("name",), ignore_case=True)
    sensitive = reader.search("PORTAGE", fields=("name",), ignore_case=False)
    assert any(r.cp == "sys-apps/portage" for r in insensitive)
    assert not any(r.cp == "sys-apps/portage" for r in sensitive)  # lowercase cp


def test_installed_size_positive_for_installed_package():
    assert reader.installed_size("sys-apps/portage") > 0
    assert reader.installed_size("no-such/package-xyz") == 0


def test_download_size_returns_int():
    assert isinstance(reader.download_size("sys-apps/portage"), int)
    assert reader.download_size("sys-apps/portage") >= 0


def test_reverse_dependencies_finds_dependents():
    # acct-user/geoclue RDEPENDs acct-group/geoclue on any Gentoo host with it
    rdeps = reader.reverse_dependencies("acct-group/geoclue")
    assert "acct-user/geoclue" in rdeps
    assert rdeps == sorted(rdeps)
    # a widely-used library has many installed dependents
    assert len(reader.reverse_dependencies("dev-libs/glib")) > 1


def test_invalidate_caches_rebuilds_index():
    first = reader.reverse_dependencies("dev-libs/glib")
    reader.invalidate_caches()
    assert reader.reverse_dependencies("dev-libs/glib") == first  # rebuilds, same data


def test_get_package_detail_has_size_and_reverse_deps():
    d = reader.get_package_detail("sys-apps/portage")
    assert d.installed_size > 0
    assert isinstance(d.download_size, int)
    assert isinstance(d.required_by, list)


def test_search_file_owner_resolves_path():
    owners = reader.search_file_owner("/bin/bash")
    assert any(r.cp == "app-shells/bash" for r in owners)
    assert all(r.installed for r in owners)  # file owners are installed


def test_search_file_owner_rejects_relative_path():
    assert reader.search_file_owner("relative/path") == []
    assert reader.search_file_owner("/no/such/file/xyzzy") == []


def test_search_description_field_runs():
    hits = reader.search("superuser", fields=("description",), limit=50)
    assert isinstance(hits, list)
    # app-admin/sudo's metadata.xml longdescription mentions "superuser"
    assert any(r.cp == "app-admin/sudo" for r in hits)
