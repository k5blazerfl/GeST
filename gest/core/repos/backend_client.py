"""Async client for the Repos backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BUS_NAME, REPOS_IFACE, REPOS_PATH


class ReposBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> ReposBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, REPOS_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, REPOS_PATH, introspection)
        self._iface = obj.get_interface(REPOS_IFACE)
        return self

    async def enable(self, name):
        return await self._iface.call_enable(name)

    async def disable(self, name):
        return await self._iface.call_disable(name)

    async def remove(self, name):
        return await self._iface.call_remove(name)

    async def add(self, name, sync_type, uri):
        return await self._iface.call_add(name, sync_type, uri)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
