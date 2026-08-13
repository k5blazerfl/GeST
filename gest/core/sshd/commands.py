"""Pure argv builders for the sshd tool. No I/O; CI-testable."""

from __future__ import annotations


def sshd_test_argv(path: str, *, sshd: str = "sshd") -> list[str]:
    """Validate a candidate config without touching the running daemon (`sshd -t -f`)."""
    return [sshd, "-t", "-f", path]
