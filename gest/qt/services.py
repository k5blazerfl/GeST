"""Services module logic: pure labels + sync bridges to the async, polkit-gated
Services backend (widget → core → backend), same pattern as gest/qt/net.py.
"""

from __future__ import annotations

from gest.core.services.model import Service
from gest.qt.backend import run_backend

_ACTIONS = ("start", "stop", "restart")


def valid_action(action: str) -> bool:
    return action in _ACTIONS


def service_label(service: Service) -> str:
    label = f"{service.name} — {service.status}"
    return label + " · enabled" if service.enabled else label


def control(name: str, action: str) -> tuple[bool, str]:
    async def run():
        from gest.core.services.backend_client import ServicesBackend

        backend = await ServicesBackend().connect()
        try:
            return await backend.control(name, action)
        finally:
            await backend.close()

    return run_backend(run)


def set_enabled(name: str, enabled: bool) -> tuple[bool, str]:
    async def run():
        from gest.core.services.backend_client import ServicesBackend

        backend = await ServicesBackend().connect()
        try:
            return await backend.set_enabled(name, enabled)
        finally:
            await backend.close()

    return run_backend(run)


def set_masked(name: str, masked: bool) -> tuple[bool, str]:
    async def run():
        from gest.core.services.backend_client import ServicesBackend

        backend = await ServicesBackend().connect()
        try:
            return await backend.set_masked(name, masked)
        finally:
            await backend.close()

    return run_backend(run)
