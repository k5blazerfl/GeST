"""CI-safe tests for the gestd Network adapter — the model->property-bag
converters (pure). The variant packing + live `ip`/netifrc reads are exercised by
the round-trip on the host."""

from gest.core.network.model import Interface
from gest.core.network.netifrc import InterfaceConfig
from gest.coreservice import network_adapter as adapter
from gest.ipc import core_contract


def test_interface_to_dict_up_and_loopback():
    eth = Interface(name="eth0", state="UP", mac="aa:bb:cc:dd:ee:ff",
                    addresses=["192.168.1.5/24", "fe80::1/64"])
    d = adapter.interface_to_dict(eth)
    assert d["name"] == "eth0" and d["state"] == "UP" and d["mac"] == "aa:bb:cc:dd:ee:ff"
    assert d["addresses"] == ["192.168.1.5/24", "fe80::1/64"]
    assert d["up"] is True and d["loopback"] is False
    assert set(d) == {"name", "state", "mac", "addresses", "up", "loopback"}
    lo = adapter.interface_to_dict(Interface(name="lo", state="DOWN"))
    assert lo["loopback"] is True and lo["up"] is False and lo["addresses"] == []


def test_config_to_dict_static_and_dhcp():
    static = InterfaceConfig(iface="eth0", method="static",
                             address="192.168.1.5/24", gateway="192.168.1.1")
    d = adapter.config_to_dict(static)
    assert d == {"iface": "eth0", "method": "static",
                 "address": "192.168.1.5/24", "gateway": "192.168.1.1"}
    dhcp = adapter.config_to_dict(InterfaceConfig(iface="wlan0", method="dhcp"))
    assert dhcp["method"] == "dhcp" and dhcp["address"] == "" and dhcp["gateway"] == ""


def test_network_contract_shape():
    assert core_contract.NETWORK_CORE_IFACE == "org.gentoo.gest.core1.Network"
    assert core_contract.NETWORK_CORE_PATH == "/org/gentoo/gest/core/Network"
