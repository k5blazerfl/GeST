"""Async client for the Users backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BUS_NAME, USERS_IFACE, USERS_PATH


class UsersBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> UsersBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, USERS_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, USERS_PATH, introspection)
        self._iface = obj.get_interface(USERS_IFACE)
        return self

    async def add_user(self, name, comment="", shell="", home="", groups="", system=False):
        return await self._iface.call_add_user(name, comment, shell, home, groups, system)

    async def modify_user(self, name, comment="", shell="", groups=""):
        return await self._iface.call_modify_user(name, comment, shell, groups)

    async def delete_user(self, name, remove_home=False):
        return await self._iface.call_delete_user(name, remove_home)

    async def add_group(self, name, system=False):
        return await self._iface.call_add_group(name, system)

    async def delete_group(self, name):
        return await self._iface.call_delete_group(name)

    async def set_password(self, name, password):
        return await self._iface.call_set_password(name, password)

    async def set_group_member(self, group, user, add):
        return await self._iface.call_set_group_member(group, user, add)

    async def set_defaults(self, group="", home="", shell="", inactive="", expire=""):
        return await self._iface.call_set_defaults(group, home, shell, inactive, expire)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
