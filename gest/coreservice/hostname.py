"""The Hostname gestd D-Bus object — a thin dbus_next wrapper over the adapter.

Only variant packing lives here; all logic is in ``hostname_adapter`` (pure) and
``gest.core`` (the real thing). This is the per-module template: subclass
``ServiceInterface``, annotate the three read methods, delegate to an adapter.
"""

from __future__ import annotations

from dbus_next import Variant
from dbus_next.service import ServiceInterface, method

from gest.coreservice import hostname_adapter as adapter
from gest.ipc.core_contract import HOSTNAME_CORE_IFACE


class HostnameInterface(ServiceInterface):
    def __init__(self) -> None:
        super().__init__(HOSTNAME_CORE_IFACE)

    @method()
    def GetState(self) -> "a{sv}":
        # Extensible property bag: add fields without a breaking arity change.
        return {k: Variant("s", v) for k, v in adapter.get_state().items()}

    @method()
    def Validate(self, name: "s") -> "bs":   # -> (ok, message)
        ok, message = adapter.validate(name)
        return [ok, message]

    @method()
    def Render(self, name: "s") -> "s":
        return adapter.render(name)
