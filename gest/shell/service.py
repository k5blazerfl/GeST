"""``org.gentoo.gest.Shell`` — the session-bus read service (HeDE Phase 2, 2a).

Runs unprivileged in the user session (HeDE autostarts it). Exposes the pending
``@world`` update count as a D-Bus property + change signal, backed by the
in-process ``core`` reader. dbus-next is imported lazily so ``gest.shell.reader``
stays testable without it.

Run with: ``gest-shell`` (or ``python -m gest.shell.service``).
"""

from __future__ import annotations

import asyncio

from gest.ipc.interface import SHELL_BUS_NAME, SHELL_IFACE, SHELL_PATH
from gest.shell.reader import update_count


def _build_interface():
    # Imported here so the module (and reader tests) don't require dbus-next.
    from dbus_next import PropertyAccess
    from dbus_next.service import ServiceInterface, dbus_property, method, signal

    class ShellInterface(ServiceInterface):
        def __init__(self) -> None:
            super().__init__(SHELL_IFACE)
            self._update_count = 0
            self._net = (False, "none", "")  # connected, kind, iface
            self._bat = (False, 0, "Unknown")  # present, percent, status

        # --- software updates ---
        @dbus_property(access=PropertyAccess.READ)
        def UpdateCount(self) -> "u":  # noqa: F821, UP037
            return self._update_count

        @signal()
        def UpdatesChanged(self, count: "u") -> "u":  # noqa: F821, UP037
            return count

        # --- network (scalar props; NetworkChanged says "re-read") ---
        @dbus_property(access=PropertyAccess.READ)
        def NetworkConnected(self) -> "b":  # noqa: F821, UP037
            return self._net[0]

        @dbus_property(access=PropertyAccess.READ)
        def NetworkKind(self) -> "s":  # noqa: F821, UP037
            return self._net[1]

        @dbus_property(access=PropertyAccess.READ)
        def NetworkIface(self) -> "s":  # noqa: F821, UP037
            return self._net[2]

        @signal()
        def NetworkChanged(self) -> None:
            pass

        # --- battery ---
        @dbus_property(access=PropertyAccess.READ)
        def BatteryPresent(self) -> "b":  # noqa: F821, UP037
            return self._bat[0]

        @dbus_property(access=PropertyAccess.READ)
        def BatteryPercent(self) -> "i":  # noqa: F821, UP037
            return self._bat[1]

        @dbus_property(access=PropertyAccess.READ)
        def BatteryStatus(self) -> "s":  # noqa: F821, UP037
            return self._bat[2]

        @signal()
        def BatteryChanged(self) -> None:
            pass

        @method()
        async def Refresh(self) -> None:
            await self.refresh()

        async def refresh(self) -> None:
            # Portage / ip / sysfs reads are blocking; keep the loop responsive.
            loop = asyncio.get_running_loop()
            count, net, bat = await loop.run_in_executor(None, _collect)
            if count != self._update_count:
                self._update_count = count
                self.emit_properties_changed({"UpdateCount": count})
                self.UpdatesChanged(count)
            if net != self._net:
                self._net = net
                self.NetworkChanged()
            if bat != self._bat:
                self._bat = bat
                self.BatteryChanged()

    return ShellInterface()


def _collect() -> tuple:
    """Gather all seam data in one blocking call (run off the event loop)."""
    from gest.core.hardware.battery import read_battery
    from gest.core.network.reader import list_interfaces, network_status

    ns = network_status(list_interfaces())
    b = read_battery()
    return (
        update_count(),
        (ns.connected, ns.kind, ns.iface),
        (b.present, b.percent, b.status),
    )


async def _amain() -> None:
    from dbus_next import BusType
    from dbus_next.aio import MessageBus

    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    iface = _build_interface()
    bus.export(SHELL_PATH, iface)
    await bus.request_name(SHELL_BUS_NAME)
    await iface.refresh()
    while True:  # periodic re-check; clients can also call Refresh()
        await asyncio.sleep(1800)
        await iface.refresh()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
