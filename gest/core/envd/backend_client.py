"""Async client for the Envd backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BUS_NAME, ENVD_IFACE, ENVD_PATH


class EnvdBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> EnvdBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, ENVD_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, ENVD_PATH, introspection)
        self._iface = obj.get_interface(ENVD_IFACE)
        return self

    async def apply_vars(self, variables: dict[str, str]):
        """Write the drop-in and run env-update; (ok, output)."""
        pairs = [[k, v] for k, v in variables.items()]
        return await self._iface.call_apply_vars(pairs)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
