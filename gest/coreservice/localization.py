"""The Localization gestd D-Bus object — timezone / locale / console keymap.

Reads the current values and the (large) pick-lists; ``Validate`` keeps the
regex/allow-list checks in Python ``core``. Applying is a write on the polkit root
backend (System). List methods walk zoneinfo / run ``locale -a`` etc., so they run
off the event loop via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio

from dbus_next.service import ServiceInterface, method

from gest.coreservice import localization_adapter as adapter
from gest.coreservice.varmap import variant_map as _vmap
from gest.ipc.core_contract import LOCALIZATION_CORE_IFACE


class LocalizationInterface(ServiceInterface):
    def __init__(self) -> None:
        super().__init__(LOCALIZATION_CORE_IFACE)

    @method()
    async def GetState(self) -> "a{sv}":
        return _vmap(await asyncio.to_thread(adapter.get_state))

    @method()
    async def ListZones(self) -> "as":
        return await asyncio.to_thread(adapter.list_zones)

    @method()
    async def ListLocales(self) -> "as":
        return await asyncio.to_thread(adapter.list_locales)

    @method()
    async def ListKeymaps(self) -> "as":
        return await asyncio.to_thread(adapter.list_keymaps)

    @method()
    async def Validate(self, field: "s", value: "s") -> "bs":   # -> (ok, message)
        ok, message = await asyncio.to_thread(adapter.validate, field, value)
        return [ok, message]
