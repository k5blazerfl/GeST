"""The Network gestd D-Bus object.

Reads link status and netifrc config over the contract. Methods are ``async`` +
``asyncio.to_thread`` — ``ListInterfaces`` shells out to ``ip`` (blocking), so it
runs off gestd's event loop like the other modules. Bringing links up/down or
writing netifrc is a write on the polkit root backend.
"""

from __future__ import annotations

import asyncio

from dbus_next.service import ServiceInterface, method

from gest.coreservice import network_adapter as adapter
from gest.coreservice.varmap import variant_map as _vmap
from gest.ipc.core_contract import NETWORK_CORE_IFACE


class NetworkInterface(ServiceInterface):
    def __init__(self) -> None:
        super().__init__(NETWORK_CORE_IFACE)

    @method()
    async def ListInterfaces(self) -> "aa{sv}":
        rows = await asyncio.to_thread(adapter.list_interfaces)
        return [_vmap(d) for d in rows]

    @method()
    async def GetConfig(self, iface: "s") -> "a{sv}":
        return _vmap(await asyncio.to_thread(adapter.get_config, iface))
