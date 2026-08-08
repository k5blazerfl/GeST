"""CI-safe tests for netifrc /etc/conf.d/net parsing and rendering."""

import pytest

from gest.core.network import netifrc

_CONF = (
    'modules="dhcpcd"\n'
    'config_eth0="dhcp"\n'
    'config_wlan0="192.168.1.5/24"\n'
    'routes_wlan0="default via 192.168.1.1"\n'
)


def test_parse_dhcp_static_and_missing():
    assert netifrc.parse_conf_net(_CONF, "eth0").method == "dhcp"
    w = netifrc.parse_conf_net(_CONF, "wlan0")
    assert w.method == "static"
    assert w.address == "192.168.1.5/24" and w.gateway == "192.168.1.1"
    assert netifrc.parse_conf_net(_CONF, "eth9").method == "none"


def test_validators():
    assert netifrc.valid_address("192.168.1.5/24")
    assert netifrc.valid_address("2001:db8::1/64")
    assert not netifrc.valid_address("192.168.1.5")   # needs a prefix
    assert not netifrc.valid_address("nope")
    assert netifrc.valid_gateway("10.0.0.1")
    assert netifrc.valid_gateway("")                  # optional
    assert not netifrc.valid_gateway("999.1.1.1")


def test_render_replaces_only_target_interface():
    cfg = netifrc.InterfaceConfig("eth0", "static", "10.0.0.2/24", "10.0.0.1")
    out = netifrc.render_conf_net(_CONF, cfg)
    # eth0 rewritten, wlan0 + modules untouched, no duplicate config_eth0
    assert out.count('config_eth0=') == 1
    assert 'config_eth0="10.0.0.2/24"' in out
    assert 'routes_eth0="default via 10.0.0.1"' in out
    assert 'config_wlan0="192.168.1.5/24"' in out
    assert 'modules="dhcpcd"' in out


def test_render_dhcp_drops_routes():
    seed = 'config_eth0="1.2.3.4/24"\nroutes_eth0="default via 1.2.3.1"\n'
    out = netifrc.render_conf_net(seed, netifrc.InterfaceConfig("eth0", "dhcp"))
    assert 'config_eth0="dhcp"' in out
    assert "routes_eth0" not in out  # DHCP supplies the gateway


@pytest.mark.parametrize("bad", ["not-a-cidr", "192.168.1.5", "192.168.1.0/33"])
def test_valid_address_rejects(bad):
    assert not netifrc.valid_address(bad)
