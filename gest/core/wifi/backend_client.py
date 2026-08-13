"""Async client for the Wifi backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BUS_NAME, WIFI_IFACE, WIFI_PATH


class WifiBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> WifiBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, WIFI_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, WIFI_PATH, introspection)
        self._iface = obj.get_interface(WIFI_IFACE)
        return self

    async def add_network(self, ssid: str, passphrase: str):
        """Add/replace a network (blank passphrase = open); (ok, output)."""
        return await self._iface.call_add_network(ssid, passphrase)

    async def remove_network(self, ssid: str):
        return await self._iface.call_remove_network(ssid)

    async def scan(self):
        """Scan for nearby SSIDs; returns (ok, [ssid, …])."""
        return await self._iface.call_scan()

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
