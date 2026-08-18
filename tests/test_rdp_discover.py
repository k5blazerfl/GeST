"""CI-safe tests for LAN RDP discovery (enumeration + scan orchestration).

The network probe is injected; the real one (probe_port) opens a socket and is
host-only, so it is not exercised here.
"""

from __future__ import annotations

import pytest

from gest.core.rdp import discover


# ---- CIDR enumeration (pure) -------------------------------------------
def test_hosts_in_slash24_excludes_network_and_broadcast():
    hosts = discover.hosts_in("192.168.1.0/24")
    assert len(hosts) == 254
    assert "192.168.1.0" not in hosts and "192.168.1.255" not in hosts
    assert "192.168.1.1" in hosts and "192.168.1.254" in hosts


def test_hosts_in_single_ip():
    assert discover.hosts_in("10.0.0.5") == ["10.0.0.5"]
    assert discover.hosts_in("10.0.0.5/32") == ["10.0.0.5"]


def test_hosts_in_tolerates_host_bits():
    # strict=False: a host address with a prefix is accepted.
    assert discover.hosts_in("192.168.1.5/24")[0] == "192.168.1.1"


def test_hosts_in_invalid_raises():
    with pytest.raises(ValueError):
        discover.hosts_in("not-a-cidr")


def test_host_count_is_cheap_and_correct():
    # counts without materialising — a /8 would be 16M addresses to enumerate.
    assert discover.host_count("10.0.0.0/8") == 2 ** 24 - 2
    assert discover.host_count("192.168.1.0/24") == 254
    assert discover.host_count("10.0.0.5/32") == 1
    with pytest.raises(ValueError):
        discover.host_count("nope")


# ---- scan orchestration (injected probe) -------------------------------
def test_scan_returns_only_open_hosts():
    open_hosts = {"192.168.1.10", "192.168.1.20"}

    def probe(host, port, timeout):
        return host in open_hosts

    found = discover.scan("192.168.1.0/24", probe=probe)
    assert {h.host for h in found} == open_hosts
    assert all(h.port == discover.RDP_PORT for h in found)
    assert all(h.name == h.host for h in found)


def test_scan_honours_port():
    seen = []

    def probe(host, port, timeout):
        seen.append(port)
        return False

    discover.scan("10.0.0.1/32", port=3390, probe=probe)
    assert seen == [3390]


def test_profile_from_discovered():
    dh = discover.DiscoveredHost(host="pc.corp", port=3390)
    profile = discover.profile_from_discovered(dh)
    assert profile.host == "pc.corp" and profile.port == 3390 and profile.name == "pc.corp"
    assert discover.profile_from_discovered(dh, name="Work").name == "Work"


# ---- CLI ---------------------------------------------------------------
def _env(tmp_path, open_hosts):
    from gest.tui.gangway.cli import CliIO, GangwayEnv
    out: list[str] = []
    err: list[str] = []
    io = CliIO(out=out.append, err=err.append, ask_password=lambda p: "")
    env = GangwayEnv(io=io, store_base=str(tmp_path / "cfg"),
                     applications_dir=str(tmp_path / "apps"),
                     port_probe=lambda host, port, timeout: host in open_hosts)
    return env, out, err


def test_cli_discover_lists_open_hosts(tmp_path):
    from gest.tui.gangway.cli import run_cli
    env, out, _ = _env(tmp_path, {"192.168.1.10"})
    assert run_cli(["discover", "192.168.1.0/24"], env=env) == 0
    assert "192.168.1.10:3389" in out
    assert any("1 host(s)" in line for line in out)


def test_cli_discover_add_saves_profiles(tmp_path):
    from gest.core.rdp import store
    from gest.tui.gangway.cli import run_cli
    env, _out, _err = _env(tmp_path, {"192.168.1.10", "192.168.1.11"})
    assert run_cli(["discover", "192.168.1.0/24", "--add"], env=env) == 0
    saved = store.list_profiles(env.store_base)
    assert set(saved) == {"192.168.1.10", "192.168.1.11"}


def test_cli_discover_refuses_large_range(tmp_path):
    from gest.tui.gangway.cli import run_cli
    env, _, err = _env(tmp_path, set())
    assert run_cli(["discover", "10.0.0.0/8", "--max", "1024"], env=env) == 2
    assert any("narrow the range" in e for e in err)


def test_cli_discover_invalid_cidr(tmp_path):
    from gest.tui.gangway.cli import run_cli
    env, _, err = _env(tmp_path, set())
    assert run_cli(["discover", "bogus"], env=env) == 2
    assert err
