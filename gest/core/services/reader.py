"""Read OpenRC service state as the invoking user (no mutations).

Combines three read-only commands:
  rc-service --list   → every available init script
  rc-update show      → which runlevels each service is enabled in
  rc-status --all     → current run status per service
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from gest.core.services.model import Service

Runner = Callable[[list[str]], str]

# The runlevels a user typically enables into (excludes internal ones for the
# "enabled" notion but we still record whatever rc-update reports).
RUNLEVELS = ("sysinit", "boot", "default", "nonetwork", "shutdown")


def _default_runner(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True).stdout
    except OSError:
        return ""


def parse_enabled(text: str) -> dict[str, list[str]]:
    """Parse `rc-update show`: lines of `service | runlevel...`."""
    enabled: dict[str, list[str]] = {}
    for line in text.splitlines():
        if "|" not in line:
            continue
        name, rest = line.split("|", 1)
        name = name.strip()
        if name:
            enabled[name] = rest.split()
    return enabled


def parse_status(text: str) -> dict[str, str]:
    """Parse `rc-status --all`: ` name    [  status  ]` lines."""
    status: dict[str, str] = {}
    for line in text.splitlines():
        if "[" in line and "]" in line:
            tokens = line.split()
            if not tokens:
                continue
            name = tokens[0]
            state = line[line.index("[") + 1 : line.index("]")].strip()
            status[name] = state
    return status


def list_services(runner: Runner | None = None) -> list[Service]:
    run = runner or _default_runner
    names = [n.strip() for n in run(["rc-service", "--list"]).splitlines() if n.strip()]
    enabled = parse_enabled(run(["rc-update", "show"]))
    status = parse_status(run(["rc-status", "--all"]))
    services = [
        Service(name=name, status=status.get(name, "stopped"), runlevels=enabled.get(name, []))
        for name in sorted(set(names))
    ]
    return services
