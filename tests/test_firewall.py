"""CI-safe tests for the firewall core: policy validation, ruleset rendering,
the render→parse round-trip, unmanaged detection, argv builders, and the reader."""

from gest.core.firewall import commands, nft, reader
from gest.core.firewall.model import FirewallPolicy

# --- validation -------------------------------------------------------------

def test_valid_port_range_and_bool_rejected():
    assert nft.valid_port(1) and nft.valid_port(22) and nft.valid_port(65535)
    assert not nft.valid_port(0)
    assert not nft.valid_port(65536)
    assert not nft.valid_port(True)          # bool is not a port


def test_valid_policy():
    assert nft.valid_policy(FirewallPolicy("drop", True, [22, 443], [53]))
    assert nft.valid_policy(FirewallPolicy("accept", False, [], []))
    assert not nft.valid_policy(FirewallPolicy("reject", True, [], []))     # bad default
    assert not nft.valid_policy(FirewallPolicy("drop", True, [70000], []))  # bad port


# --- rendering --------------------------------------------------------------

def test_render_includes_base_rules_and_policy():
    text = nft.render_ruleset(FirewallPolicy("drop", True, [22, 80], [51820]))
    assert text.startswith("#!/usr/sbin/nft -f\n")
    assert nft.MARKER in text
    assert "type filter hook input priority 0; policy drop;" in text
    assert "ct state established,related accept" in text
    assert 'iif "lo" accept' in text
    assert "ip protocol icmp accept" in text           # allow_ping
    assert "tcp dport { 22, 80 } accept" in text
    assert "udp dport { 51820 } accept" in text
    assert "chain forward" in text and "chain output" in text


def test_render_omits_ping_and_empty_port_sets():
    text = nft.render_ruleset(FirewallPolicy("accept", False, [], []))
    assert "policy accept;" in text
    assert "ip protocol icmp accept" not in text       # ping off
    assert "echo-request" not in text
    assert "tcp dport" not in text                     # no ports
    assert "udp dport" not in text


# --- render -> parse round-trip ---------------------------------------------

def test_parse_round_trips_the_policy():
    for policy in (
        FirewallPolicy("drop", True, [22, 80, 443], [53, 67]),
        FirewallPolicy("accept", False, [], []),
        FirewallPolicy("drop", False, [8080], []),
    ):
        assert nft.parse_ruleset(nft.render_ruleset(policy)) == policy


def test_parse_returns_none_for_unmanaged_or_missing_marker():
    assert nft.parse_ruleset("table inet filter { chain input { } }") is None
    assert nft.parse_ruleset("") is None
    # marker present but no gest: line -> still unmanaged
    assert nft.parse_ruleset(f"{nft.MARKER}\ntable inet filter {{}}\n") is None


# --- argv builders ----------------------------------------------------------

def test_nft_argv_builders():
    assert commands.nft_check_argv("/etc/nftables.nft") == \
        ["nft", "-c", "-f", "/etc/nftables.nft"]
    assert commands.nft_load_argv("/etc/nftables.nft") == ["nft", "-f", "/etc/nftables.nft"]
    assert commands.nft_list_argv() == ["nft", "list", "ruleset"]
    assert commands.nft_flush_argv() == ["nft", "flush", "ruleset"]


# --- reader -----------------------------------------------------------------

def test_current_policy_and_is_managed(tmp_path):
    p = tmp_path / "nftables.nft"
    policy = FirewallPolicy("drop", True, [22], [])
    p.write_text(nft.render_ruleset(policy))
    assert reader.current_policy(str(p)) == policy
    assert reader.is_managed(str(p))
    # a hand-written / absent ruleset is not managed
    (tmp_path / "hand.nft").write_text("table inet x { }\n")
    assert reader.current_policy(str(tmp_path / "hand.nft")) is None
    assert not reader.is_managed(str(tmp_path / "missing.nft"))


def test_nft_available_via_fake_runner():
    assert reader.nft_available(lambda argv: (0, "nftables v1.0.9"))
    assert not reader.nft_available(lambda argv: (127, ""))
