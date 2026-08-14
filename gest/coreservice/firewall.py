"""The Firewall gestd D-Bus object — smart-detected status + per-backend config."""

from __future__ import annotations

import asyncio

from dbus_next.service import ServiceInterface, method

from gest.coreservice import firewall_adapter as adapter
from gest.coreservice.varmap import variant_map as _vmap
from gest.ipc.core_contract import FIREWALL_CORE_IFACE


class FirewallInterface(ServiceInterface):
    def __init__(self) -> None:
        super().__init__(FIREWALL_CORE_IFACE)

    @method()
    async def Status(self) -> "a{sv}":
        return _vmap(await asyncio.to_thread(adapter.status))

    @method()
    async def GetNftPolicy(self) -> "a{sv}":
        return _vmap(await asyncio.to_thread(adapter.nft_policy))

    @method()
    async def GetFirewalldZone(self, zone: "s") -> "a{sv}":
        return _vmap(await asyncio.to_thread(adapter.firewalld_zone, zone))
