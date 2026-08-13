"""Async client for the Firewalld backend interface (dbus-next)."""

from __future__ import annotations

from collections.abc import Iterable

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BUS_NAME, FIREWALLD_IFACE, FIREWALLD_PATH


class FirewalldBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> FirewalldBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, FIREWALLD_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, FIREWALLD_PATH, introspection)
        self._iface = obj.get_interface(FIREWALLD_IFACE)
        return self

    async def apply_changes(
        self,
        zone: str,
        add_services: Iterable[str],
        remove_services: Iterable[str],
        add_ports: Iterable[str],
        remove_ports: Iterable[str],
    ):
        """Apply a staged services/ports diff at the permanent scope, then reload
        so it takes effect live; returns ``(ok, output)``."""
        return await self._iface.call_apply_changes(
            zone,
            list(add_services),
            list(remove_services),
            list(add_ports),
            list(remove_ports),
        )

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
