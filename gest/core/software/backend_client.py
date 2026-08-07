"""Async client the frontend uses to reach the root backend.

This is the *only* part of ``core`` that mutates the system, and it does so
indirectly — every call goes over the system bus to ``gest-backend``. It uses
dbus-next so it integrates with the frontend's asyncio loop (Textual's).

If the backend is not installed/running, :func:`connect` raises; callers should
treat that as "privileged operations unavailable" rather than crashing.
"""

from __future__ import annotations

from collections.abc import Callable

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BUS_NAME, SOFTWARE_IFACE, SOFTWARE_PATH


class SoftwareBackend:
    """A thin async wrapper over the ``org.gentoo.gest.Software`` interface."""

    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> "SoftwareBackend":
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, SOFTWARE_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, SOFTWARE_PATH, introspection)
        self._iface = obj.get_interface(SOFTWARE_IFACE)
        return self

    async def install_preview(self, atom: str) -> str:
        """Return the `emerge --pretend` report for ``atom``."""
        return await self._iface.call_install_preview(atom)

    async def install(
        self,
        atom: str,
        on_progress: Callable[[str], None] | None = None,
        on_finished: Callable[[int], None] | None = None,
    ) -> bool:
        """Start a merge; stream output through the supplied callbacks.

        Returns True once the backend has accepted and started the merge (i.e.
        polkit authorized the caller). Raises on access-denied.
        """
        if on_progress is not None:
            self._iface.on_progress(lambda line: on_progress(line))
        if on_finished is not None:
            self._iface.on_finished(lambda code: on_finished(code))
        return await self._iface.call_install(atom)

    async def set_package_config(self, kind: str, atom: str, line: str) -> bool:
        """Write ``line`` for ``atom`` into package.<kind>/gest (polkit-gated)."""
        return await self._iface.call_set_package_config(kind, atom, line)

    async def rebuild(
        self,
        atom: str,
        on_progress=None,
        on_finished=None,
    ) -> bool:
        """Rebuild ``atom`` (emerge --changed-use); streams like install."""
        if on_progress is not None:
            self._iface.on_progress(lambda line: on_progress(line))
        if on_finished is not None:
            self._iface.on_finished(lambda code: on_finished(code))
        return await self._iface.call_rebuild(atom)

    async def set_package_use(self, atom: str, line: str) -> bool:
        """Write ``line`` for ``atom`` into package.use/gest (polkit-gated)."""
        return await self._iface.call_set_package_use(atom, line)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
