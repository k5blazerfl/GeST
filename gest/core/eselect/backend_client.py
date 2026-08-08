"""Async client for the Eselect backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BUS_NAME, ESELECT_IFACE, ESELECT_PATH


class EselectBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> EselectBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, ESELECT_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, ESELECT_PATH, introspection)
        self._iface = obj.get_interface(ESELECT_IFACE)
        return self

    async def set_target(self, module: str, target):
        return await self._iface.call_set_target(module, str(target))

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
