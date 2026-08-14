"""sshd module logic: pure summary + a sync bridge to the Sshd backend."""

from __future__ import annotations

from gest.core.sshd.model import SshdSettings
from gest.qt.backend import run_backend


def sshd_summary(s: SshdSettings) -> str:
    auth = "on" if s.password_authentication else "off"
    return f"port {s.port} · root login: {s.permit_root_login} · password auth: {auth}"


def apply_config(settings: SshdSettings) -> tuple[bool, str]:
    async def run():
        from gest.core.sshd.backend_client import SshdBackend

        backend = await SshdBackend().connect()
        try:
            return await backend.apply_config(settings)
        finally:
            await backend.close()

    return run_backend(run)
