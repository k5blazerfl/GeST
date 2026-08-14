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

from gest.coreservice.catalog import CatalogInterface
from gest.coreservice.descriptors import MODULES
from gest.coreservice.disk import DiskInterface
from gest.coreservice.firewall import FirewallInterface
from gest.coreservice.hostname import HostnameInterface
from gest.coreservice.localization import LocalizationInterface
from gest.coreservice.network import NetworkInterface
from gest.coreservice.services import ServicesInterface
from gest.coreservice.software import SoftwareInterface
from gest.coreservice.sysctl import SysctlInterface
from gest.coreservice.users import UsersInterface
from gest.ipc.core_contract import CATALOG_CORE_PATH, CORE_BUS_NAME

# Descriptor id -> the ServiceInterface class that implements it. The registry in
# ``descriptors`` is the single source of the paths/metadata; this maps each to
# its implementation. The assertion fails loudly if the two ever drift.
_FACTORIES = {
    "hostname": HostnameInterface,
    "localization": LocalizationInterface,
    "sysctl": SysctlInterface,
    "services": ServicesInterface,
    "users": UsersInterface,
    "software": SoftwareInterface,
    "network": NetworkInterface,
    "firewall": FirewallInterface,
    "disk": DiskInterface,
}
assert {m.id for m in MODULES} == set(_FACTORIES), "descriptor/factory registry drift"


async def _serve() -> None:
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    for m in MODULES:
        bus.export(m.path, _FACTORIES[m.id]())
    bus.export(CATALOG_CORE_PATH, CatalogInterface())   # module enumeration
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
