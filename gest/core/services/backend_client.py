"""Async client for the Services backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BUS_NAME, SERVICES_IFACE, SERVICES_PATH


class ServicesBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> "ServicesBackend":
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, SERVICES_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, SERVICES_PATH, introspection)
        self._iface = obj.get_interface(SERVICES_IFACE)
        return self

    async def control(self, name: str, action: str):
        """Start/stop/restart a service. Returns [ok, output]."""
        return await self._iface.call_control(name, action)

    async def set_enabled(self, name: str, enabled: bool, runlevel: str = "default"):
        """Enable/disable a service in a runlevel. Returns [ok, output]."""
        return await self._iface.call_set_enabled(name, enabled, runlevel)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
