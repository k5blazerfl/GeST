"""CI-safe tests for the network core (JSON parsing + argv builder)."""

import pytest

from gest.core.network import commands, reader

_SAMPLE = (
    '[{"ifname":"lo","operstate":"UNKNOWN","address":"00:00:00:00:00:00",'
    '"addr_info":[{"family":"inet","local":"127.0.0.1","prefixlen":8}]},'
    '{"ifname":"eth0","operstate":"UP","address":"aa:bb:cc:dd:ee:ff",'
    '"addr_info":[{"family":"inet","local":"192.168.1.5","prefixlen":24},'
    '{"family":"inet6","local":"fe80::1","prefixlen":64}]}]'
)


def test_parse_ip_json():
    ifs = reader.parse_ip_json(_SAMPLE)
    by = {i.name: i for i in ifs}
    assert by["lo"].loopback and not by["lo"].up
    assert by["eth0"].up
    assert by["eth0"].mac == "aa:bb:cc:dd:ee:ff"
    assert by["eth0"].addresses == ["192.168.1.5/24", "fe80::1/64"]


def test_parse_ip_json_bad_input():
    assert reader.parse_ip_json("not json") == []
    assert reader.parse_ip_json("") == []


def test_iplink_argv():
    assert commands.iplink_argv("eth0", True) == ["ip", "link", "set", "eth0", "up"]
    assert commands.iplink_argv("eth0", False) == ["ip", "link", "set", "eth0", "down"]
    assert commands.iplink_argv("br0", True, ip="/sbin/ip")[0] == "/sbin/ip"


@pytest.mark.parametrize("bad", ["", "bad iface", "a;rm", "eth0 up"])
def test_iplink_rejects_bad_iface(bad):
    with pytest.raises(ValueError):
        commands.iplink_argv(bad, True)
