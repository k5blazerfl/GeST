"""env.d module logic: a sync bridge to the Envd backend."""

from __future__ import annotations

from gest.qt.backend import run_backend


def apply_vars(variables: dict[str, str]) -> tuple[bool, str]:
    async def run():
        from gest.core.envd.backend_client import EnvdBackend

        backend = await EnvdBackend().connect()
        try:
            return await backend.apply_vars(variables)
        finally:
            await backend.close()

    return run_backend(run)
