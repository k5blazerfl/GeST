"""Async client for the System backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BUS_NAME, SYSTEM_IFACE, SYSTEM_PATH


class SystemBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> SystemBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, SYSTEM_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, SYSTEM_PATH, introspection)
        self._iface = obj.get_interface(SYSTEM_IFACE)
        return self

    async def set_hostname(self, name):
        return await self._iface.call_set_hostname(name)

    async def set_timezone(self, zone):
        return await self._iface.call_set_timezone(zone)

    async def set_locale(self, lang):
        return await self._iface.call_set_locale(lang)

    async def set_keymap(self, keymap):
        return await self._iface.call_set_keymap(keymap)

    async def set_console_font(self, font):
        return await self._iface.call_set_console_font(font)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
