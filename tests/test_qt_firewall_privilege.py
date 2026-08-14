"""Tests for the Firewall + Privilege pure summaries."""

from gest.core.firewall.model import FirewallPolicy
from gest.core.privilege.model import EscalationPolicy
from gest.qt.firewall import policy_summary
from gest.qt.privilege import escalation_summary


def test_firewall_summary():
    assert policy_summary(None, False, False) == "nftables not available"
    assert policy_summary(None, False, True) == "not managed by GeST"
    p = FirewallPolicy(default_input="drop", allow_ping=True, tcp_ports=[22, 80])
    assert policy_summary(p, True, True) == "default input: drop · ping: allowed · open TCP: 22, 80"


def test_escalation_summary():
    assert escalation_summary("sudo", None) == "sudo: not configured by GeST"
    p = EscalationPolicy(tool="doas", group="wheel", passwordless=True)
    assert escalation_summary("doas", p) == "doas: group wheel · passwordless"
