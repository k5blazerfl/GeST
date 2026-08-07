"""Read OpenRC service state as the invoking user (no mutations).

Combines three read-only commands:
  rc-service --list   → every available init script
  rc-update show      → which runlevels each service is enabled in
  rc-status --all     → current run status per service
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from gest.core.services.model import Service, ServiceDetail

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


def _words(text: str) -> list[str]:
    """Split OpenRC dependency output into a sorted, de-duplicated name list."""
    return sorted({w for w in text.split() if w})


def parse_describe(text: str) -> str:
    """Pull a one-line description out of `rc-service X describe` output.

    OpenRC prefixes lines with ` * ` (and some scripts lead with `name:`); the
    first meaningful line is the service's own description.
    """
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("*"):
            line = line[1:].strip()
        if not line:
            continue
        # Drop a leading "servicename:" label if the script uses one.
        if ":" in line:
            head, _, tail = line.partition(":")
            if head and " " not in head and tail.strip():
                line = tail.strip()
        return line
    return ""


def describe_service(
    name: str,
    runner: Runner | None = None,
    *,
    status: str = "stopped",
    runlevels: list[str] | None = None,
) -> ServiceDetail:
    """Introspect one service via read-only `rc-service` sub-commands.

    `status`/`runlevels` are passed through from an already-loaded Service so we
    don't re-run `rc-status`; everything else comes from the init script's own
    dependency metadata.
    """
    run = runner or _default_runner
    return ServiceDetail(
        name=name,
        description=parse_describe(run(["rc-service", name, "describe"])),
        needs=_words(run(["rc-service", name, "ineed"])),
        uses=_words(run(["rc-service", name, "iuse"])),
        wants=_words(run(["rc-service", name, "iwant"])),
        needed_by=_words(run(["rc-service", name, "needsme"])),
        status=status,
        runlevels=list(runlevels or []),
    )
