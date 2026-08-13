"""Async client for the Stage3 backend interface (dbus-next).

Unpack streams like the kernel-build client: ``unpack`` wires the
Progress/Finished signal callbacks and returns once the backend has authorized
and started the run (download + verify + unpack runs for minutes, so it is a
streaming call, never a blocking one).
"""

from __future__ import annotations

from collections.abc import Callable

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.interface import BUS_NAME, STAGE3_IFACE, STAGE3_PATH


class Stage3Backend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> Stage3Backend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, STAGE3_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, STAGE3_PATH, introspection)
        self._iface = obj.get_interface(STAGE3_IFACE)
        return self

    async def unpack(
        self,
        target_root: str,
        tarball_url: str,
        digests_text: str,
        signature_url: str,
        on_progress: Callable[[list[str]], None] | None = None,
        on_finished: Callable[[int], None] | None = None,
    ) -> bool:
        """Start a stage3 download+verify+unpack into ``target_root``; stream
        output through the callbacks. Returns True once the backend has
        authorized and started it.

        ``digests_text`` is the raw ``.DIGESTS`` file text (the frontend fetches
        the small index/DIGESTS unprivileged via ``index.fetch_text``); the
        backend re-parses it and runs the mandatory hash check server-side.
        """
        if on_progress is not None:
            self._iface.on_progress(on_progress)
        if on_finished is not None:
            self._iface.on_finished(on_finished)
        return await self._iface.call_unpack(
            target_root, tarball_url, digests_text, signature_url)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
