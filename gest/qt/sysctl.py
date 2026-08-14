"""sysctl module logic: pure merge + a sync bridge to the Sysctl backend."""

from __future__ import annotations

from gest.qt.backend import run_backend


def merged_settings(current: dict[str, str], key: str, value: str) -> dict[str, str]:
    """Current settings with `key=value` set (so applying doesn't drop others)."""
    out = dict(current)
    out[key] = value
    return out


def apply_settings(settings: dict[str, str]) -> tuple[bool, str]:
    async def run():
        from gest.core.sysctl.backend_client import SysctlBackend

        backend = await SysctlBackend().connect()
        try:
            return await backend.apply_settings(settings)
        finally:
            await backend.close()

    return run_backend(run)
