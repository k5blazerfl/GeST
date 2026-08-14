"""Services module logic: pure labels + sync bridges to the async, polkit-gated
Services backend (widget → core → backend), same pattern as gest/qt/net.py.
"""

from __future__ import annotations

import asyncio

from gest.core.services.model import Service

_ACTIONS = ("start", "stop", "restart")


def valid_action(action: str) -> bool:
    return action in _ACTIONS


def service_label(service: Service) -> str:
    label = f"{service.name} — {service.status}"
    return label + " · enabled" if service.enabled else label


def _call(coro_factory) -> tuple[bool, str]:
    """Run an async backend call that returns [ok, output]; → (ok, message)."""
    try:
        result = asyncio.run(coro_factory())
        ok = bool(result[0])
        msg = str(result[1]) if len(result) > 1 else ""
        return (ok, msg)
    except Exception as e:  # surface backend/D-Bus/polkit errors to the UI
        return (False, str(e))


def control(name: str, action: str) -> tuple[bool, str]:
    async def run():
        from gest.core.services.backend_client import ServicesBackend

        backend = await ServicesBackend().connect()
        try:
            return await backend.control(name, action)
        finally:
            await backend.close()

    return _call(run)


def set_enabled(name: str, enabled: bool, runlevel: str = "default") -> tuple[bool, str]:
    async def run():
        from gest.core.services.backend_client import ServicesBackend

        backend = await ServicesBackend().connect()
        try:
            return await backend.set_enabled(name, enabled, runlevel)
        finally:
            await backend.close()

    return _call(run)
