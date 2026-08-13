"""Async client for the Network backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BUS_NAME, NETWORK_IFACE, NETWORK_PATH


class NetworkBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> NetworkBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, NETWORK_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, NETWORK_PATH, introspection)
        self._iface = obj.get_interface(NETWORK_IFACE)
        return self

    async def set_link(self, iface, up):
        return await self._iface.call_set_link(iface, up)

    async def set_interface_config(self, iface, method, address="", gateway="", root: str = "/"):
        return await self._iface.call_set_interface_config(
            iface, method, address, gateway, root)

    async def set_resolvers(self, nameservers, search, root: str = "/"):
        return await self._iface.call_set_resolvers(nameservers, search, root)

    async def set_hosts(self, entries, root: str = "/"):
        """entries: list of (address, [names])."""
        return await self._iface.call_set_hosts(entries, root)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
