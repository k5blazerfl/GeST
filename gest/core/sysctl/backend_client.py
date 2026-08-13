"""Async client for the Sysctl backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BUS_NAME, SYSCTL_IFACE, SYSCTL_PATH


class SysctlBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> SysctlBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, SYSCTL_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, SYSCTL_PATH, introspection)
        self._iface = obj.get_interface(SYSCTL_IFACE)
        return self

    async def apply_settings(self, settings: dict[str, str], root: str = "/"):
        """Write the drop-in and load it with sysctl -p; (ok, output)."""
        pairs = [[k, v] for k, v in settings.items()]
        return await self._iface.call_apply_settings(pairs, root)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
