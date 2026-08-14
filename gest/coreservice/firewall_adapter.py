"""Pure adapter for the Firewall core module (nftables + firewalld).

Exposes the smart-detected status plus each backend's current config. Applying a
policy stays a write on the polkit root backend.
"""

from __future__ import annotations

from typing import Any

from gest.core import firewall_detect
from gest.core.firewall import reader as nft_reader
from gest.core.firewalld import reader as fwd_reader


def status_to_dict(st: Any) -> dict[str, Any]:
    return {
        "firewalld_installed": st.firewalld_installed,
        "firewalld_running": st.firewalld_running,
        "nftables_installed": st.nftables_installed,
        "nftables_active": st.nftables_active,
        "active": st.active,
    }


def policy_to_dict(p: Any) -> dict[str, Any]:
    """An nftables FirewallPolicy (or None if unmanaged) -> property bag."""
    if p is None:
        return {"managed": False, "default_input": "", "allow_ping": False,
                "tcp_ports": [], "udp_ports": []}
    return {
        "managed": True,
        "default_input": p.default_input,
        "allow_ping": p.allow_ping,
        "tcp_ports": [str(x) for x in p.tcp_ports],
        "udp_ports": [str(x) for x in p.udp_ports],
    }


def zone_to_dict(z: Any) -> dict[str, Any]:
    return {"zone": z.zone, "services": sorted(z.services), "ports": sorted(z.ports)}


def status() -> dict[str, Any]:
    return status_to_dict(firewall_detect.detect())


def nft_policy() -> dict[str, Any]:
    return policy_to_dict(nft_reader.current_policy())


def firewalld_zone(zone: str) -> dict[str, Any]:
    return zone_to_dict(fwd_reader.zone_config(zone))
