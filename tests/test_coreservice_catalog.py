"""CI-safe tests for the gestd module catalog — the descriptor registry and its
property-bag conversion (pure). Also guards that every descriptor's path/interface
matches the contract, so the registry can't drift from the module definitions."""

from gest.coreservice import catalog_adapter as adapter
from gest.coreservice.descriptors import MODULES
from gest.ipc import core_contract


def test_lists_all_nine_modules_with_unique_ids():
    rows = adapter.list_modules()
    assert len(rows) == 9
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == 9
    assert set(ids) == {"hostname", "localization", "sysctl", "services", "users",
                        "software", "network", "firewall", "disk"}


def test_descriptor_to_dict_shape():
    d = adapter.descriptor_to_dict(MODULES[0])
    assert set(d) == {"id", "title", "category", "icon", "path", "interface"}
    assert d["id"] == "hostname" and d["title"] == "Hostname"
    assert d["path"] == core_contract.HOSTNAME_CORE_PATH
    assert d["interface"] == core_contract.HOSTNAME_CORE_IFACE


def test_categories_are_grouped():
    cats = {r["id"]: r["category"] for r in adapter.list_modules()}
    assert cats["software"] == "Software"
    assert cats["network"] == "Network"
    assert cats["disk"] == "Hardware"
    assert cats["hostname"] == "System"
    assert cats["services"] == "Services"
    assert cats["users"] == "Users & Security" and cats["firewall"] == "Users & Security"


def test_every_descriptor_matches_a_contract_constant():
    # each descriptor's id maps to the FOO_CORE_PATH / FOO_CORE_IFACE contract
    # constants — so the registry can't drift from the module definitions.
    for m in MODULES:
        assert m.iface.startswith("org.gentoo.gest.core1.")
        assert m.path.startswith("/org/gentoo/gest/core/")
        prefix = m.id.upper()
        assert getattr(core_contract, f"{prefix}_CORE_PATH") == m.path
        assert getattr(core_contract, f"{prefix}_CORE_IFACE") == m.iface


def test_catalog_contract_shape():
    assert core_contract.CATALOG_CORE_IFACE == "org.gentoo.gest.core1.Catalog"
    assert core_contract.CATALOG_CORE_PATH == "/org/gentoo/gest/core"
