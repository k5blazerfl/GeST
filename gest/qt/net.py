"""Network module logic: validation (pure) + sync bridges to the async,
polkit-gated Network backend (widget → core → backend).

The mutation helpers run the dbus-next backend call in a short-lived asyncio
loop so a PySide slot can call them synchronously; the polkit prompt is handled
by the session's polkit agent. dbus-next is imported lazily so validate_static
stays importable/testable without it.
"""

from __future__ import annotations

import asyncio

from gest.core.network.netifrc import valid_address, valid_gateway


def validate_static(address: str, gateway: str) -> str:
    """Empty string if a static config is valid, else a user-facing error."""
    if not valid_address(address):
        return "Address must be CIDR, e.g. 192.168.1.10/24"
    if not valid_gateway(gateway):
        return "Gateway must be a valid IP address"
    return ""


def _run(coro) -> tuple[bool, str]:
    try:
        asyncio.run(coro)
        return (True, "")
    except Exception as e:
        return (False, str(e))


def apply_interface_config(iface: str, method: str, address: str = "",
                           gateway: str = "") -> tuple[bool, str]:
    async def run() -> None:
        from gest.core.network.backend_client import NetworkBackend

        backend = await NetworkBackend().connect()
        try:
            await backend.set_interface_config(iface, method, address, gateway)
        finally:
            await backend.close()

    return _run(run())


def set_link(iface: str, up: bool) -> tuple[bool, str]:
    async def run() -> None:
        from gest.core.network.backend_client import NetworkBackend

        backend = await NetworkBackend().connect()
        try:
            await backend.set_link(iface, up)
        finally:
            await backend.close()

    return _run(run())
