"""The Services (OpenRC) gestd D-Bus object.

Reads service status + runlevels over the contract. Methods are ``async`` and run
the blocking ``rc-*`` subprocess reads in a worker thread (``asyncio.to_thread``),
so they never block gestd's event loop — the same "reads off the loop" rule the
Software module follows. Starting/stopping/enabling remains a write on the polkit
root backend.
"""

from __future__ import annotations

import asyncio

from dbus_next.service import ServiceInterface, method

from gest.coreservice import services_adapter as adapter
from gest.coreservice.varmap import variant_map as _vmap
from gest.ipc.core_contract import SERVICES_CORE_IFACE


class ServicesInterface(ServiceInterface):
    def __init__(self) -> None:
        super().__init__(SERVICES_CORE_IFACE)

    @method()
    async def List(self) -> "aa{sv}":
        rows = await asyncio.to_thread(adapter.list_services)
        return [_vmap(d) for d in rows]

    @method()
    async def Describe(self, name: "s") -> "a{sv}":
        return _vmap(await asyncio.to_thread(adapter.describe, name))
