"""Privilege (sudo/doas) module logic: pure summary + set bridges."""

from __future__ import annotations

from gest.core.privilege.model import EscalationPolicy
from gest.qt.backend import run_backend


def escalation_summary(tool: str, policy: EscalationPolicy | None) -> str:
    if policy is None:
        return f"{tool}: not configured by GeST"
    pw = "passwordless" if policy.passwordless else "password required"
    return f"{tool}: group {policy.group} · {pw}"


def set_sudo(group: str, enabled: bool, passwordless: bool) -> tuple[bool, str]:
    async def run():
        from gest.core.privilege.backend_client import PrivilegeBackend

        backend = await PrivilegeBackend().connect()
        try:
            return await backend.set_sudo(group, enabled, passwordless)
        finally:
            await backend.close()

    return run_backend(run)


def set_doas(group: str, enabled: bool, passwordless: bool) -> tuple[bool, str]:
    async def run():
        from gest.core.privilege.backend_client import PrivilegeBackend

        backend = await PrivilegeBackend().connect()
        try:
            return await backend.set_doas(group, enabled, passwordless, True)
        finally:
            await backend.close()

    return run_backend(run)
