"""The declarative firewall policy the module renders to an nftables ruleset."""

from __future__ import annotations

from dataclasses import dataclass, field

INPUT_POLICIES = ("drop", "accept")


@dataclass(slots=True, frozen=True)
class FirewallPolicy:
    """A simple stateful firewall.

    ``default_input`` is the input chain's base policy (``"drop"`` for a locked-
    down host, ``"accept"`` for an open one). ``allow_ping`` opens ICMP echo.
    ``tcp_ports`` / ``udp_ports`` are the inbound ports to accept regardless of
    the default policy. Established/related traffic, loopback and IPv6 neighbour
    discovery are always allowed by the renderer so a ``drop`` policy stays usable.
    """

    default_input: str = "drop"
    allow_ping: bool = True
    tcp_ports: list[int] = field(default_factory=list)
    udp_ports: list[int] = field(default_factory=list)
