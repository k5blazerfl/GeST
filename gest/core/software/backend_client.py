"""Async client the frontend uses to reach the root backend.

This is the *only* part of ``core`` that mutates the system, and it does so
indirectly — every call goes over the system bus to ``gest-backend``. It uses
dbus-next so it integrates with the frontend's asyncio loop (urwid's).

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

    async def connect(self) -> SoftwareBackend:
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
        on_progress: Callable[[list[str]], None] | None = None,
        on_finished: Callable[[int], None] | None = None,
    ) -> bool:
        """Start a merge; stream output through the supplied callbacks.

        ``on_progress`` receives a *batch* of output lines per call — the backend
        coalesces emerge output to avoid a signal-per-line storm.

        Returns True once the backend has accepted and started the merge (i.e.
        polkit authorized the caller). Raises on access-denied.
        """
        if on_progress is not None:
            self._iface.on_progress(on_progress)
        if on_finished is not None:
            self._iface.on_finished(on_finished)
        return await self._iface.call_install(atom)

    async def install_multi(self, atoms, on_progress=None, on_finished=None) -> bool:
        """Merge several atoms in one emerge; streams like install."""
        if on_progress is not None:
            self._iface.on_progress(on_progress)
        if on_finished is not None:
            self._iface.on_finished(on_finished)
        return await self._iface.call_install_multi(atoms)

    async def install_binary_multi(self, atoms, only, on_progress=None,
                                   on_finished=None) -> bool:
        """Merge atoms as binary packages (--getbinpkg [--usepkgonly]); streams."""
        if on_progress is not None:
            self._iface.on_progress(on_progress)
        if on_finished is not None:
            self._iface.on_finished(on_finished)
        return await self._iface.call_install_binary_multi(atoms, only)

    async def rebuild(
        self,
        atom: str,
        on_progress=None,
        on_finished=None,
    ) -> bool:
        """Rebuild ``atom`` (emerge --changed-use); streams like install."""
        if on_progress is not None:
            self._iface.on_progress(on_progress)
        if on_finished is not None:
            self._iface.on_finished(on_finished)
        return await self._iface.call_rebuild(atom)

    async def sync(self, on_progress=None, on_finished=None) -> bool:
        """Sync the Portage tree (emerge --sync); streams like install."""
        if on_progress is not None:
            self._iface.on_progress(on_progress)
        if on_finished is not None:
            self._iface.on_finished(on_finished)
        return await self._iface.call_sync()

    async def sync_repos(self, names) -> tuple[bool, str]:
        """Sync specific repositories (emaint sync --repo <name>) and wait.

        Returns ``(ok, output)`` — ``ok`` is True only if every named repo
        synced. Blocking (no streaming); used by the refresh-on-open step.
        """
        return await self._iface.call_sync_repos(list(names))

    async def depclean(self, atom: str = "", on_progress=None, on_finished=None) -> bool:
        """Remove packages via emerge --depclean [atom]; streams like install."""
        if on_progress is not None:
            self._iface.on_progress(on_progress)
        if on_finished is not None:
            self._iface.on_finished(on_finished)
        return await self._iface.call_depclean(atom)

    async def update_world(self, on_progress=None, on_finished=None) -> bool:
        """Update the system (emerge -uDN @world); streams like install."""
        if on_progress is not None:
            self._iface.on_progress(on_progress)
        if on_finished is not None:
            self._iface.on_finished(on_finished)
        return await self._iface.call_update_world()

    async def mark_news_read(self, selector: str) -> bool:
        """Mark Portage news read (polkit-gated). selector: "all"/"new"/number."""
        return await self._iface.call_mark_news_read(selector)

    async def depclean_multi(self, atoms, on_progress=None, on_finished=None) -> bool:
        """Remove several atoms in one emerge --depclean; streams like install."""
        if on_progress is not None:
            self._iface.on_progress(on_progress)
        if on_finished is not None:
            self._iface.on_finished(on_finished)
        return await self._iface.call_depclean_multi(atoms)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
