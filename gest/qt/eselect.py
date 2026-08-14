"""eselect module logic: pure target label + a sync bridge to the backend."""

from __future__ import annotations

from gest.core.eselect.model import Target
from gest.qt.backend import run_backend


def target_label(target: Target) -> str:
    return f"{target.name} (current)" if target.current else target.name


def set_target(module: str, target: str) -> tuple[bool, str]:
    async def run():
        from gest.core.eselect.backend_client import EselectBackend

        backend = await EselectBackend().connect()
        try:
            return await backend.set_target(module, target)
        finally:
            await backend.close()

    return run_backend(run)
