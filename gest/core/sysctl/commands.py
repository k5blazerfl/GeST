"""Pure argv builders for sysctl. No I/O; CI-testable."""

from __future__ import annotations


def sysctl_load_argv(path: str, *, sysctl: str = "sysctl") -> list[str]:
    """Load (apply) a sysctl config file into the running kernel (`sysctl -p`)."""
    return [sysctl, "-p", path]


def sysctl_read_argv(key: str, *, sysctl: str = "sysctl") -> list[str]:
    """Read a single live value (`sysctl -n <key>`)."""
    return [sysctl, "-n", key]
