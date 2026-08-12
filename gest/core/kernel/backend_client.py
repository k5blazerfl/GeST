"""Async client for the Kernel backend interface (dbus-next).

Build streams like the software client: ``build`` wires the Progress/Finished
signal callbacks and returns once the backend has authorized and started the run.
"""

from __future__ import annotations

from collections.abc import Callable

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.core.kernel.build import BuildConfig
from gest.ipc.interface import BUS_NAME, KERNEL_IFACE, KERNEL_PATH


class KernelBackend:
    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._iface = None

    async def connect(self) -> KernelBackend:
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._bus.introspect(BUS_NAME, KERNEL_PATH)
        obj = self._bus.get_proxy_object(BUS_NAME, KERNEL_PATH, introspection)
        self._iface = obj.get_interface(KERNEL_IFACE)
        return self

    async def build(
        self,
        config: BuildConfig,
        on_progress: Callable[[list[str]], None] | None = None,
        on_finished: Callable[[int], None] | None = None,
    ) -> bool:
        """Start a kernel build; stream output through the callbacks. Returns True
        once the backend has authorized and started it."""
        if on_progress is not None:
            self._iface.on_progress(on_progress)
        if on_finished is not None:
            self._iface.on_finished(on_finished)
        return await self._iface.call_build(
            config.method, config.source_dir, int(config.jobs),
            config.kernel_config, config.initramfs, config.kver)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
            self._iface = None
