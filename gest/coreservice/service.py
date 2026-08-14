"""``gestd`` entry point — claim the session-bus name and export the modules.

Run it as ``gest-core`` (the console script). Each module registered here exports
one object; Phase-0 ships Hostname. The C++/Qt HeDE shell (or the Python reference
client) then calls those objects for reads/validation/render, and the polkit root
backend for writes.
"""

from __future__ import annotations

import asyncio
import sys

from dbus_next import BusType
from dbus_next.aio import MessageBus

from gest.coreservice.hostname import HostnameInterface
from gest.coreservice.services import ServicesInterface
from gest.coreservice.software import SoftwareInterface
from gest.coreservice.users import UsersInterface
from gest.ipc.core_contract import (
    CORE_BUS_NAME,
    HOSTNAME_CORE_PATH,
    SERVICES_CORE_PATH,
    SOFTWARE_CORE_PATH,
    USERS_CORE_PATH,
)

# (object path, interface factory) for every module gestd exports.
_MODULES = [
    (HOSTNAME_CORE_PATH, HostnameInterface),
    (SOFTWARE_CORE_PATH, SoftwareInterface),
    (SERVICES_CORE_PATH, ServicesInterface),
    (USERS_CORE_PATH, UsersInterface),
]


async def _serve() -> None:
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    for path, factory in _MODULES:
        bus.export(path, factory())
    await bus.request_name(CORE_BUS_NAME)
    await bus.wait_for_disconnect()


def main() -> None:
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        sys.stderr.write(f"gest-core: could not start ({exc}). Is the session D-Bus running?\n")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
