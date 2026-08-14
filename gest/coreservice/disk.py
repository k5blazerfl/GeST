"""The Disks & mounts gestd D-Bus object — block devices + mount points."""

from __future__ import annotations

import asyncio

from dbus_next.service import ServiceInterface, method

from gest.coreservice import disk_adapter as adapter
from gest.coreservice.varmap import variant_map as _vmap
from gest.ipc.core_contract import DISK_CORE_IFACE


class DiskInterface(ServiceInterface):
    def __init__(self) -> None:
        super().__init__(DISK_CORE_IFACE)

    @method()
    async def List(self) -> "aa{sv}":
        rows = await asyncio.to_thread(adapter.list_devices)
        return [_vmap(d) for d in rows]
