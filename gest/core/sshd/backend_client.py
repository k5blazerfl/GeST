"""Async client for the Sshd backend interface (dbus-next)."""

from __future__ import annotations

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.core.sshd.model import SshdSettings
from gest.ipc.interface import BUS_NAME, SSHD_IFACE, SSHD_PATH


class SshdBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> SshdBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, SSHD_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, SSHD_PATH, introspection)
        self._iface = obj.get_interface(SSHD_IFACE)
        return self

    async def apply_config(self, settings: SshdSettings, root: str = "/"):
        """Upsert + validate (sshd -t) + write sshd_config and reload; (ok, output)."""
        return await self._iface.call_apply_config(
            settings.port,
            settings.permit_root_login,
            settings.password_authentication,
            settings.pubkey_authentication,
            settings.x11_forwarding,
            settings.permit_empty_passwords,
            root,
        )

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
