"""The Software gestd D-Bus object — the Portage-heavy reads over the contract.

This is the module that proves path B: a C++/Qt client gets rich package data
(installed / updates / search / detail / counts) and never touches the Portage
Python API. Only variant packing lives here; the shapes are in
``software_adapter`` (pure) and the queries in ``gest.core.software.reader``.

The methods are ``async`` and run the actual Portage read in a worker thread via
``asyncio.to_thread``: Portage's synchronous API drives its *own* asyncio loop
internally (``portdbapi.aux_get`` → ``run_until_complete``), which raises "event
loop is already running" if called directly inside gestd's dbus event loop. This
mirrors the TUI's ``run_blocking`` — Portage reads must run off the loop.
"""

from __future__ import annotations

import asyncio
from typing import Any

from dbus_next import Variant
from dbus_next.service import ServiceInterface, method

from gest.coreservice import software_adapter as adapter
from gest.ipc.core_contract import SOFTWARE_CORE_IFACE


def _v(value: Any) -> Variant:
    """Wrap a Python scalar/list in the right D-Bus Variant (bool before int!)."""
    if isinstance(value, bool):
        return Variant("b", value)
    if isinstance(value, int):
        return Variant("x", value)          # int64 (sizes can be large)
    if isinstance(value, list):
        return Variant("as", [str(x) for x in value])
    return Variant("s", str(value))


def _vmap(d: dict[str, Any]) -> dict[str, Variant]:
    return {k: _v(v) for k, v in d.items()}


class SoftwareInterface(ServiceInterface):
    def __init__(self) -> None:
        super().__init__(SOFTWARE_CORE_IFACE)

    @method()
    async def ListInstalled(self) -> "aa{sv}":
        rows = await asyncio.to_thread(adapter.list_installed)
        return [_vmap(d) for d in rows]

    @method()
    async def ListUpgradable(self) -> "aa{sv}":
        rows = await asyncio.to_thread(adapter.list_upgradable)
        return [_vmap(d) for d in rows]

    @method()
    async def Search(self, term: "s", fields: "as", mode: "s",
                     ignore_case: "b", limit: "i") -> "aa{sv}":
        rows = await asyncio.to_thread(
            adapter.search, term, list(fields), mode, ignore_case, limit)
        return [_vmap(d) for d in rows]

    @method()
    async def PackagesInCategory(self, category: "s", limit: "i") -> "aa{sv}":
        rows = await asyncio.to_thread(adapter.packages_in_category, category, limit)
        return [_vmap(d) for d in rows]

    @method()
    async def ListCategories(self) -> "as":
        return await asyncio.to_thread(adapter.list_categories)

    @method()
    async def GetDetail(self, cp: "s") -> "a{sv}":
        return _vmap(await asyncio.to_thread(adapter.get_detail, cp))

    @method()
    async def Counts(self) -> "a{sx}":
        return await asyncio.to_thread(adapter.counts)
