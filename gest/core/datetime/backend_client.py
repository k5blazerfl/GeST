"""Async client for the DateTime backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BUS_NAME, DATETIME_IFACE, DATETIME_PATH


class DateTimeBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> DateTimeBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, DATETIME_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, DATETIME_PATH, introspection)
        self._iface = obj.get_interface(DATETIME_IFACE)
        return self

    async def set_clock(self, timestamp: str):
        return await self._iface.call_set_clock(timestamp)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
