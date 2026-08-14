"""Reference client for the gestd contract — a HeDE Qt view in miniature.

Proves the round-trip. In one terminal run ``gest-core``; in another run
``python -m gest.coreservice.refclient``. A C++/Qt view does exactly this against
the same introspectable interface (via ``qdbusxml2cpp``-generated bindings).
"""

from __future__ import annotations

import asyncio

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.ipc.core_contract import (
    CORE_BUS_NAME,
    HOSTNAME_CORE_IFACE,
    HOSTNAME_CORE_PATH,
)


async def _run() -> None:
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    intro = await bus.introspect(CORE_BUS_NAME, HOSTNAME_CORE_PATH)
    obj = bus.get_proxy_object(CORE_BUS_NAME, HOSTNAME_CORE_PATH, intro)
    iface = obj.get_interface(HOSTNAME_CORE_IFACE)

    state = await iface.call_get_state()
    print("GetState :", {k: v.value for k, v in state.items()})
    for candidate in ("my-host", "bad host!"):
        ok, message = await iface.call_validate(candidate)
        print(f"Validate({candidate!r}) : ok={ok} message={message!r}")
    print("Render('my-host') :", repr(await iface.call_render("my-host")))
    bus.disconnect()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
