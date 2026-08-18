"""Discover RDP hosts on the local network by probing for an open RDP port.

Pure enumeration + orchestration; the actual TCP probe is injected. Its default,
:func:`probe_port`, opens a socket, so it is **host-only** (like a live launch)
— but the CIDR math and the scan loop are unit-testable with a fake probe.

mDNS is deliberately not used: Windows RDP does not advertise a ``_rdp._tcp``
service by default, so a port scan of a CIDR is the reliable path.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass

from gest.core.rdp.model import RdpProfile

RDP_PORT = 3389

# (host, port, timeout_seconds) -> is the port open?
Probe = Callable[[str, int, float], bool]


@dataclass(slots=True)
class DiscoveredHost:
    host: str
    port: int = RDP_PORT
    name: str = ""


def host_count(cidr: str) -> int:
    """How many usable hosts a CIDR covers — **cheap** (does not materialise the
    addresses), so a caller can reject a huge range before enumerating it. Raises
    ``ValueError`` on a malformed range."""
    net = ipaddress.ip_network(cidr, strict=False)
    if net.num_addresses <= 2:  # /32 → 1, /31 → 2 (RFC 3021, both usable)
        return net.num_addresses
    return net.num_addresses - 2  # exclude network + broadcast


def hosts_in(cidr: str) -> list[str]:
    """Usable host addresses in a CIDR (or a single address). Raises
    ``ValueError`` on a malformed range. ``strict=False`` tolerates host bits
    set (``192.168.1.5/24``). For huge ranges, gate on :func:`host_count` first."""
    net = ipaddress.ip_network(cidr, strict=False)
    return [str(host) for host in net.hosts()]


def probe_port(host: str, port: int, timeout: float = 0.3) -> bool:
    """Default probe — a TCP connect. Host-only (touches the network)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def scan(cidr: str, *, port: int = RDP_PORT, probe: Probe = probe_port,
         timeout: float = 0.3) -> list[DiscoveredHost]:
    """Probe every host in ``cidr`` for ``port`` and return the ones that answer.
    Sequential — a real front-end should parallelise; the scaffold keeps it simple."""
    found: list[DiscoveredHost] = []
    for host in hosts_in(cidr):
        if probe(host, port, timeout):
            found.append(DiscoveredHost(host=host, port=port, name=host))
    return found


def profile_from_discovered(discovered: DiscoveredHost, name: str = "") -> RdpProfile:
    """Turn a discovered host into a candidate profile (other fields default)."""
    return RdpProfile(name=name or discovered.name or discovered.host,
                      host=discovered.host, port=discovered.port)
