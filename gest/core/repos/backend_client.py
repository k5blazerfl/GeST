"""Async client for the Repos backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import (
    BUS_NAME,
    REPOS_IFACE,
    REPOS_PATH,
    SSH_IFACE,
    SSH_PATH,
)


class ReposBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> ReposBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, REPOS_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, REPOS_PATH, introspection)
        self._iface = obj.get_interface(REPOS_IFACE)
        return self

    async def enable(self, name):
        return await self._iface.call_enable(name)

    async def disable(self, name):
        return await self._iface.call_disable(name)

    async def remove(self, name):
        return await self._iface.call_remove(name)

    async def add(self, name, sync_type, uri):
        return await self._iface.call_add(name, sync_type, uri)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None


class SshBackend:
    """Async client for the SSH deploy-key interface (dbus-next)."""

    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> SshBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, SSH_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, SSH_PATH, introspection)
        self._iface = obj.get_interface(SSH_IFACE)
        return self

    async def deploy_key(self):
        """(has_key, public_key, path) — reads the existing key, no auth."""
        return await self._iface.call_deploy_key()

    async def ensure_deploy_key(self):
        """(ok, public_key, path, message) — generate if missing (polkit-gated)."""
        return await self._iface.call_ensure_deploy_key()

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
