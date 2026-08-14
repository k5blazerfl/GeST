"""Firewall module logic: pure status summary + enable-at-boot bridge."""

from __future__ import annotations

from gest.core.firewall.model import FirewallPolicy
from gest.qt.backend import run_backend


def policy_summary(policy: FirewallPolicy | None, managed: bool, nft_ok: bool) -> str:
    if not nft_ok:
        return "nftables not available"
    if policy is None or not managed:
        return "not managed by GeST"
    ports = ", ".join(str(p) for p in policy.tcp_ports) or "none"
    ping = "allowed" if policy.allow_ping else "blocked"
    return f"default input: {policy.default_input} · ping: {ping} · open TCP: {ports}"


def enable_at_boot() -> tuple[bool, str]:
    async def run():
        from gest.core.firewall.backend_client import FirewallBackend

        backend = await FirewallBackend().connect()
        try:
            return await backend.enable_at_boot()
        finally:
            await backend.close()

    return run_backend(run)
