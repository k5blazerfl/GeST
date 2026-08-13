"""CI-safe tests for the firewalld core: validators, argv builders (all
--permanent), output parsers, the reader over a fake runner, and a ZoneConfig
round-trip."""

import pytest

from gest.core.firewalld import commands, parse, reader
from gest.core.firewalld.model import ZoneConfig

# --- validators -------------------------------------------------------------

def test_valid_zone():
    assert commands.valid_zone("public")
    assert commands.valid_zone("my-zone_1")
    assert not commands.valid_zone("")
    assert not commands.valid_zone("bad zone")       # space
    assert not commands.valid_zone("drop;rm")         # punctuation


def test_valid_service():
    assert commands.valid_service("ssh")
    assert commands.valid_service("dhcpv6-client")
    assert not commands.valid_service("SSH")          # uppercase
    assert not commands.valid_service("-lead")        # leading dash
    assert not commands.valid_service("has space")


def test_valid_port():
    assert commands.valid_port("22/tcp")
    assert commands.valid_port("65535/udp")
    assert not commands.valid_port("22")              # no proto
    assert not commands.valid_port("0/tcp")           # out of range
    assert not commands.valid_port("70000/tcp")       # out of range
    assert not commands.valid_port("22/sctp")         # bad proto


# --- argv builders (all list/mutate at --permanent) -------------------------

def test_query_builders():
    assert commands.get_default_zone_argv() == ["firewall-cmd", "--get-default-zone"]
    assert commands.list_all_zones_argv() == ["firewall-cmd", "--get-zones"]
    assert commands.get_services_argv() == ["firewall-cmd", "--get-services"]
    assert commands.reload_argv() == ["firewall-cmd", "--reload"]


def test_list_builders_are_permanent():
    assert commands.list_services_argv("public") == \
        ["firewall-cmd", "--permanent", "--zone", "public", "--list-services"]
    assert commands.list_ports_argv("public") == \
        ["firewall-cmd", "--permanent", "--zone", "public", "--list-ports"]


def test_service_mutation_builders():
    assert commands.add_service_argv("public", "ssh") == \
        ["firewall-cmd", "--permanent", "--zone", "public", "--add-service", "ssh"]
    assert commands.remove_service_argv("public", "ssh") == \
        ["firewall-cmd", "--permanent", "--zone", "public", "--remove-service", "ssh"]


def test_port_mutation_builders():
    assert commands.add_port_argv("public", "22/tcp") == \
        ["firewall-cmd", "--permanent", "--zone", "public", "--add-port", "22/tcp"]
    assert commands.remove_port_argv("public", "22/tcp") == \
        ["firewall-cmd", "--permanent", "--zone", "public", "--remove-port", "22/tcp"]


def test_custom_firewall_cmd_path():
    assert commands.add_service_argv("public", "ssh", firewall_cmd="/usr/bin/firewall-cmd")[0] \
        == "/usr/bin/firewall-cmd"


def test_builders_reject_bad_input():
    with pytest.raises(ValueError):
        commands.list_services_argv("bad zone")
    with pytest.raises(ValueError):
        commands.add_service_argv("public", "Bad Service")
    with pytest.raises(ValueError):
        commands.add_port_argv("public", "22")


# --- parsers ----------------------------------------------------------------

def test_parse_services_and_ports():
    assert parse.parse_services("ssh http https") == frozenset({"ssh", "http", "https"})
    assert parse.parse_services("") == frozenset()
    assert parse.parse_ports("22/tcp 51820/udp") == frozenset({"22/tcp", "51820/udp"})


def test_parse_zone_list_sorted():
    assert parse.parse_zone_list("public work home dmz") == ["dmz", "home", "public", "work"]


def test_parse_default_zone():
    assert parse.parse_default_zone("public\n") == "public"
    assert parse.parse_default_zone("  home ") == "home"


# --- reader over a fake runner ----------------------------------------------

def _runner(mapping):
    def run(argv):
        return mapping.get(tuple(argv), (1, ""))
    return run


def test_default_zone_and_known_services():
    run = _runner({
        ("firewall-cmd", "--get-default-zone"): (0, "public\n"),
        ("firewall-cmd", "--get-services"): (0, "ssh http https dns\n"),
    })
    assert reader.default_zone(run) == "public"
    assert reader.known_services(run) == frozenset({"ssh", "http", "https", "dns"})
    assert reader.firewalld_available(run)


def test_zone_config_over_fake_runner():
    run = _runner({
        ("firewall-cmd", "--permanent", "--zone", "public", "--list-services"):
            (0, "ssh dhcpv6-client\n"),
        ("firewall-cmd", "--permanent", "--zone", "public", "--list-ports"):
            (0, "22/tcp 443/tcp\n"),
    })
    cfg = reader.zone_config("public", run)
    assert cfg == ZoneConfig("public",
                             frozenset({"ssh", "dhcpv6-client"}),
                             frozenset({"22/tcp", "443/tcp"}))


def test_zone_config_best_effort_on_failure():
    # A read that fails yields empties, never raises.
    cfg = reader.zone_config("public", _runner({}))
    assert cfg == ZoneConfig("public", frozenset(), frozenset())
    # An invalid zone short-circuits to empties without building an argv.
    assert reader.zone_config("bad zone", _runner({})) == ZoneConfig("bad zone")


def test_zone_config_round_trip():
    cfg = ZoneConfig("home", frozenset({"ssh"}), frozenset({"80/tcp"}))
    assert cfg.zone == "home"
    assert cfg.services == frozenset({"ssh"})
    assert cfg.ports == frozenset({"80/tcp"})
