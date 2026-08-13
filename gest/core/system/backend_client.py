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

    async def set_hostname(self, name, root: str = "/"):
        return await self._iface.call_set_hostname(name, root)

    async def set_timezone(self, zone, root: str = "/"):
        return await self._iface.call_set_timezone(zone, root)

    async def set_locale(self, lang, root: str = "/"):
        return await self._iface.call_set_locale(lang, root)

    async def set_keymap(self, keymap, root: str = "/"):
        return await self._iface.call_set_keymap(keymap, root)

    async def set_console_font(self, font, root: str = "/"):
        return await self._iface.call_set_console_font(font, root)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
