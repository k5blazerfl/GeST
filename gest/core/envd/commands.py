"""Pure argv builders for env-update. No I/O; CI-testable."""

from __future__ import annotations


def env_update_argv(*, env_update: str = "env-update") -> list[str]:
    """Regenerate /etc/profile.env from /etc/env.d/ (`env-update`)."""
    return [env_update]
