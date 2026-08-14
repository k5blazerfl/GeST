"""CI-safe tests for the gestd Firewall adapter (pure converters + contract)."""

from gest.core.firewall.model import FirewallPolicy
from gest.core.firewall_detect import FirewallStatus
from gest.core.firewalld.model import ZoneConfig
from gest.coreservice import firewall_adapter as adapter
from gest.ipc import core_contract


def test_status_to_dict_and_active():
    st = FirewallStatus(firewalld_installed=True, firewalld_running=True,
                        nftables_installed=True, nftables_active=False)
    d = adapter.status_to_dict(st)
    assert d["firewalld_running"] is True and d["nftables_active"] is False
    assert d["active"] == "firewalld"
    assert set(d) == {"firewalld_installed", "firewalld_running",
                      "nftables_installed", "nftables_active", "active"}


def test_policy_to_dict_managed_and_unmanaged():
    assert adapter.policy_to_dict(None) == {
        "managed": False, "default_input": "", "allow_ping": False,
        "tcp_ports": [], "udp_ports": []}
    p = FirewallPolicy(default_input="drop", allow_ping=True,
                       tcp_ports=[22, 80], udp_ports=[53])
    d = adapter.policy_to_dict(p)
    assert d["managed"] is True and d["default_input"] == "drop" and d["allow_ping"] is True
    assert d["tcp_ports"] == ["22", "80"] and d["udp_ports"] == ["53"]


def test_zone_to_dict_sorts():
    z = ZoneConfig(zone="public", services=frozenset({"ssh", "dhcpv6-client"}),
                   ports=frozenset({"80/tcp", "22/tcp"}))
    d = adapter.zone_to_dict(z)
    assert d["zone"] == "public"
    assert d["services"] == ["dhcpv6-client", "ssh"] and d["ports"] == ["22/tcp", "80/tcp"]


def test_firewall_contract_shape():
    assert core_contract.FIREWALL_CORE_IFACE == "org.gentoo.gest.core1.Firewall"
    assert core_contract.FIREWALL_CORE_PATH == "/org/gentoo/gest/core/Firewall"
