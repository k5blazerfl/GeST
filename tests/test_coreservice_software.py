"""CI-safe tests for the gestd Software adapter — the model->property-bag
converters (pure; no D-Bus, no Portage) and the contract shape. The variant
packing and live queries are exercised by the round-trip on the Gentoo host."""

from gest.core.software.model import Package, PackageDetail, SearchResult
from gest.coreservice import software_adapter as adapter
from gest.ipc import core_contract


def test_pkg_to_dict_shape_and_values():
    p = Package(cp="app-x/y", version="1.0", slot="0", description="d",
                repository="gentoo", homepage="h", installed=True, from_binary=True,
                world_member=True, available_version="1.1")
    d = adapter.pkg_to_dict(p)
    assert d["cp"] == "app-x/y" and d["version"] == "1.0"
    assert d["repository"] == "gentoo"
    assert d["installed"] is True and d["from_binary"] is True and d["world_member"] is True
    assert d["available_version"] == "1.1"
    assert isinstance(d["upgradable"], bool)
    assert set(d) == {"cp", "version", "slot", "description", "repository", "homepage",
                      "installed", "from_binary", "world_member", "available_version",
                      "upgradable"}


def test_result_to_dict_installed_and_not():
    r = SearchResult(cp="a/b", best_version="2.0", description="d",
                     installed_version="1.9", repository="gest")
    d = adapter.result_to_dict(r)
    assert d["installed"] is True and d["installed_version"] == "1.9"
    assert d["cp"] == "a/b" and d["best_version"] == "2.0" and d["repository"] == "gest"
    # a not-installed hit → installed False, installed_version normalised to ""
    d2 = adapter.result_to_dict(SearchResult(cp="c/d", best_version="1.0"))
    assert d2["installed"] is False and d2["installed_version"] == ""


def test_detail_to_dict_scalars_and_lists():
    det = PackageDetail(cp="a/b", available_version="2.0", installed_version="1.9",
                        installed_size=1024, download_size=512, from_binary=True,
                        required_by=["c/d", "e/f"], repository="gentoo",
                        other_repos=["overlayx"])
    d = adapter.detail_to_dict(det)
    assert d["installed_size"] == 1024 and d["download_size"] == 512
    assert d["required_by"] == ["c/d", "e/f"] and d["other_repos"] == ["overlayx"]
    assert d["from_binary"] is True and d["repository"] == "gentoo"


def test_software_contract_shape():
    assert core_contract.SOFTWARE_CORE_IFACE == "org.gentoo.gest.core1.Software"
    assert core_contract.SOFTWARE_CORE_PATH == "/org/gentoo/gest/core/Software"
