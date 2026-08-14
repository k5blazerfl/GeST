"""Tests for the connectivity summary (gest.core.network.reader.network_status)."""

from gest.core.network.model import Interface
from gest.core.network.reader import network_status


def test_ethernet_wins():
    ifs = [
        Interface("lo", state="UP", addresses=["127.0.0.1/8"]),
        Interface("enp3s0", state="UP", addresses=["192.168.1.5/24"]),
    ]
    st = network_status(ifs)
    assert st.connected and st.kind == "ethernet" and st.iface == "enp3s0"


def test_wifi_by_name():
    st = network_status([Interface("wlp2s0", state="UP", addresses=["10.0.0.2/24"])])
    assert st.connected and st.kind == "wifi"


def test_offline_when_down_or_no_address():
    ifs = [
        Interface("enp3s0", state="DOWN", addresses=["1.2.3.4/24"]),
        Interface("wlp2s0", state="UP", addresses=[]),  # up but no IP
    ]
    st = network_status(ifs)
    assert not st.connected and st.kind == "none" and st.iface == ""
