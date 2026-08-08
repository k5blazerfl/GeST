"""Async client for the Bootloader backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BOOTLOADER_IFACE, BOOTLOADER_PATH, BUS_NAME


class BootloaderBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> BootloaderBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, BOOTLOADER_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, BOOTLOADER_PATH, introspection)
        self._iface = obj.get_interface(BOOTLOADER_IFACE)
        return self

    async def regenerate_grub(self):
        return await self._iface.call_regenerate_grub()

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
