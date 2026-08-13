"""Render a :class:`FirewallPolicy` to an nftables ruleset, and read it back.

The rendered file is a complete ``inet`` table with a locked-down default and the
usual safety rules (established/related, loopback, IPv6 neighbour discovery)
always present. A machine-readable ``# gest:`` comment encodes the policy so the
module can reconstruct a :class:`FirewallPolicy` from its own output — and
distinguish a GeST-managed ruleset from a hand-written one (in which case
:func:`parse_ruleset` returns ``None`` and the UI leaves it untouched).

Everything here is pure and CI-testable; the backend re-renders from validated
primitives so no caller-supplied nftables text is ever written.
"""

from __future__ import annotations

from gest.core.firewall.model import INPUT_POLICIES, FirewallPolicy

MARKER = "# Managed by GeST"
NFT_PATH = "/etc/nftables.nft"

# Always-on rules that keep a `drop` default usable (state tracking, loopback,
# and the IPv6 neighbour-discovery types a v6 host needs to function).
_BASE_RULES = (
    "ct state established,related accept",
    "ct state invalid drop",
    'iif "lo" accept',
    "icmpv6 type { nd-neighbor-solicit, nd-neighbor-advert, "
    "nd-router-solicit, nd-router-advert } accept",
)


def valid_port(port: int) -> bool:
    return isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535


def valid_policy(policy: FirewallPolicy) -> bool:
    return (
        policy.default_input in INPUT_POLICIES
        and all(valid_port(p) for p in policy.tcp_ports)
        and all(valid_port(p) for p in policy.udp_ports)
    )


def _port_set(ports: list[int]) -> str:
    return "{ " + ", ".join(str(p) for p in ports) + " }"


def _gest_line(policy: FirewallPolicy) -> str:
    return (
        f"# gest: default_input={policy.default_input} "
        f"allow_ping={'yes' if policy.allow_ping else 'no'} "
        f"tcp={','.join(str(p) for p in policy.tcp_ports)} "
        f"udp={','.join(str(p) for p in policy.udp_ports)}"
    )


def render_ruleset(policy: FirewallPolicy) -> str:
    """Render ``policy`` to a complete nftables ruleset file."""
    input_rules = list(_BASE_RULES)
    if policy.allow_ping:
        input_rules.append("ip protocol icmp accept")
        input_rules.append("icmpv6 type echo-request accept")
    if policy.tcp_ports:
        input_rules.append(f"tcp dport {_port_set(policy.tcp_ports)} accept")
    if policy.udp_ports:
        input_rules.append(f"udp dport {_port_set(policy.udp_ports)} accept")

    lines = [
        "#!/usr/sbin/nft -f",
        f"{MARKER} — simple stateful firewall.",
        "# The 'gest:' line below encodes the policy; edit it via GeST, not by hand.",
        _gest_line(policy),
        "",
        "flush ruleset",
        "",
        "table inet filter {",
        "\tchain input {",
        f"\t\ttype filter hook input priority 0; policy {policy.default_input};",
    ]
    lines += [f"\t\t{rule}" for rule in input_rules]
    lines += [
        "\t}",
        "\tchain forward {",
        "\t\ttype filter hook forward priority 0; policy drop;",
        "\t}",
        "\tchain output {",
        "\t\ttype filter hook output priority 0; policy accept;",
        "\t}",
        "}",
    ]
    return "\n".join(lines) + "\n"


def _parse_ports(value: str) -> list[int]:
    ports: list[int] = []
    for raw in value.split(","):
        token = raw.strip()
        if token.isdigit():
            ports.append(int(token))
    return ports


def parse_ruleset(text: str) -> FirewallPolicy | None:
    """Reconstruct a :class:`FirewallPolicy` from GeST-rendered ruleset text.

    Returns ``None`` if the text isn't GeST-managed (no marker / no ``gest:``
    line), so the caller can treat a hand-written ruleset as read-only.
    """
    if MARKER not in text:
        return None
    fields: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# gest:"):
            for token in stripped[len("# gest:"):].split():
                key, _, val = token.partition("=")
                fields[key] = val
            break
    else:
        return None
    default_input = fields.get("default_input", "drop")
    if default_input not in INPUT_POLICIES:
        default_input = "drop"
    return FirewallPolicy(
        default_input=default_input,
        allow_ping=fields.get("allow_ping", "yes") == "yes",
        tcp_ports=_parse_ports(fields.get("tcp", "")),
        udp_ports=_parse_ports(fields.get("udp", "")),
    )
