"""The Users & Groups gestd D-Bus object.

Reads /etc/passwd and /etc/group over the contract, with each user's group
memberships computed in. Methods are ``async`` + ``asyncio.to_thread`` to keep the
(small, but blocking) file reads off gestd's event loop, consistent with the other
modules. Creating/modifying users remains a write on the polkit root backend.
"""

from __future__ import annotations

import asyncio

from dbus_next.service import ServiceInterface, method

from gest.coreservice import users_adapter as adapter
from gest.coreservice.varmap import variant_map as _vmap
from gest.ipc.core_contract import USERS_CORE_IFACE


class UsersInterface(ServiceInterface):
    def __init__(self) -> None:
        super().__init__(USERS_CORE_IFACE)

    @method()
    async def ListUsers(self) -> "aa{sv}":
        rows = await asyncio.to_thread(adapter.list_users)
        return [_vmap(d) for d in rows]

    @method()
    async def ListGroups(self) -> "aa{sv}":
        rows = await asyncio.to_thread(adapter.list_groups)
        return [_vmap(d) for d in rows]
