"""Async client for the Firewall backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.core.firewall.model import FirewallPolicy
from gest.ipc.interface import BUS_NAME, FIREWALL_IFACE, FIREWALL_PATH


class FirewallBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> FirewallBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, FIREWALL_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, FIREWALL_PATH, introspection)
        self._iface = obj.get_interface(FIREWALL_IFACE)
        return self

    async def apply_policy(self, policy: FirewallPolicy):
        """Validate + render + write /etc/nftables.nft and load it; (ok, output)."""
        return await self._iface.call_apply_policy(
            policy.default_input, policy.allow_ping,
            list(policy.tcp_ports), list(policy.udp_ports),
        )

    async def enable_at_boot(self):
        """Persist the live ruleset and enable the nftables service; (ok, output)."""
        return await self._iface.call_enable_at_boot()

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
