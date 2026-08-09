"""Async client for the unified Portage-configuration backend (dbus-next).

Wraps the single ``WriteConfig`` method: hand it a list of
:class:`~gest.core.portage.write.ConfigWrite` and it applies them atomically as
root, after re-validating each against its surface. If the backend is not
running, :meth:`connect` raises; callers treat that as "privileged operations
unavailable" rather than crashing.
"""

from __future__ import annotations

from collections.abc import Sequence

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.core.portage.write import ConfigWrite
from gest.ipc.interface import BUS_NAME, PORTAGE_IFACE, PORTAGE_PATH


class PortageBackend:
    """A thin async wrapper over the ``org.gentoo.gest.Portage`` interface."""

    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> PortageBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, PORTAGE_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, PORTAGE_PATH, introspection)
        self._iface = obj.get_interface(PORTAGE_IFACE)
        return self

    async def write_config(self, writes: Sequence[ConfigWrite]) -> bool:
        """Apply ``writes`` under /etc/portage atomically (polkit-gated)."""
        payload = [[w.path, w.text, w.mode] for w in writes]
        return await self._iface.call_write_config(payload)

    async def setup_trust(self) -> tuple[bool, str]:
        """Run ``getuto`` to set up the binary-package trust keyring (polkit-gated)."""
        return await self._iface.call_setup_trust()

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
