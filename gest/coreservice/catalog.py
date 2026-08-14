"""The Catalog gestd D-Bus object — module enumeration for the Control Center.

A client calls ``List`` on the top-level core object to discover every module and
how to reach it, then talks to each module's own object. In-memory data, so no
worker thread needed.
"""

from __future__ import annotations

from dbus_next.service import ServiceInterface, method

from gest.coreservice import catalog_adapter as adapter
from gest.coreservice.varmap import variant_map as _vmap
from gest.ipc.core_contract import CATALOG_CORE_IFACE


class CatalogInterface(ServiceInterface):
    def __init__(self) -> None:
        super().__init__(CATALOG_CORE_IFACE)

    @method()
    def List(self) -> "aa{sv}":
        return [_vmap(d) for d in adapter.list_modules()]
