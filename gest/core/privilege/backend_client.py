"""Async client for the Privilege backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BUS_NAME, PRIVILEGE_IFACE, PRIVILEGE_PATH


class PrivilegeBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> PrivilegeBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, PRIVILEGE_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, PRIVILEGE_PATH, introspection)
        self._iface = obj.get_interface(PRIVILEGE_IFACE)
        return self

    async def set_sudo(self, group: str, enabled: bool, passwordless: bool, root: str = "/"):
        """Install (validated) or remove the GeST sudoers drop-in; (ok, output)."""
        return await self._iface.call_set_sudo(group, enabled, passwordless, root)

    async def set_doas(self, group: str, enabled: bool, passwordless: bool,
                       persist: bool, root: str = "/"):
        """Upsert or strip the GeST doas.conf block (validated); (ok, output)."""
        return await self._iface.call_set_doas(group, enabled, passwordless, persist, root)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
