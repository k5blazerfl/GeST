"""Async client for the Disk backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BUS_NAME, DISK_IFACE, DISK_PATH


class DiskBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> DiskBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, DISK_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, DISK_PATH, introspection)
        self._iface = obj.get_interface(DISK_IFACE)
        return self

    async def mount(self, mountpoint):
        return await self._iface.call_mount(mountpoint)

    async def unmount(self, mountpoint):
        return await self._iface.call_unmount(mountpoint)

    async def write_fstab_entry(self, spec, mountpoint, fstype, options, dump=0, passno=0):
        return await self._iface.call_write_fstab_entry(
            spec, mountpoint, fstype, options, dump, passno
        )

    async def remove_fstab_entry(self, mountpoint):
        return await self._iface.call_remove_fstab_entry(mountpoint)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
