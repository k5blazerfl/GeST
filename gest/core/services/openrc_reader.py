"""Read OpenRC service state as the invoking user (no mutations).

Combines three read-only commands:
  rc-service --list   → every available init script
  rc-update show      → which runlevels each service is enabled in
  rc-status --all     → current run status per service

Results are normalized onto the shared :class:`Service` / :class:`ServiceDetail`
model so the adapter, gestd contract, and both frontends stay init-agnostic:
OpenRC's ``started/stopped/crashed`` map to systemd's ``active/inactive/failed``
vocabulary, ``enabled_state`` becomes ``enabled`` when the service is in any
runlevel, and the raw runlevels ride along in ``Service.runlevels``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from gest.core.services.model import Service, ServiceDetail

Runner = Callable[[list[str]], str]

# The runlevels a user typically enables into; we still record whatever
# rc-update reports even if it is outside this set.
RUNLEVELS = ("sysinit", "boot", "default", "nonetwork", "shutdown")

# OpenRC run status → systemd ActiveState vocabulary (so the shared model's
# `running`/frontends read identically across inits).
_STATUS_MAP = {
    "started": "active",
    "starting": "activating",
    "stopped": "inactive",
    "stopping": "deactivating",
    "inactive": "inactive",
    "crashed": "failed",
    "failed": "failed",
}


def _default_runner(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True).stdout
    except OSError:
        return ""


def _norm_status(raw: str) -> str:
    return _STATUS_MAP.get(raw.strip().lower(), raw.strip().lower() or "inactive")


def parse_enabled(text: str) -> dict[str, list[str]]:
    """Parse `rc-update show`: lines of ``service | runlevel...``."""
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
    """Parse `rc-status --all`: `` name    [  status  ]`` lines."""
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
    services = []
    for name in sorted(set(names) | set(enabled)):
        runlevels = enabled.get(name, [])
        services.append(Service(
            name=name,
            status=_norm_status(status.get(name, "stopped")),
            enabled_state="enabled" if runlevels else "disabled",
            runlevels=runlevels,
        ))
    return services


def _words(text: str) -> list[str]:
    """Split OpenRC dependency output into a sorted, de-duplicated name list."""
    return sorted({w for w in text.split() if w})


def parse_describe(text: str) -> str:
    """Pull a one-line description out of `rc-service X describe` output.

    OpenRC prefixes lines with `` * `` (and some scripts lead with ``name:``);
    the first meaningful line is the service's own description.
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
    status: str = "inactive",
    enabled_state: str = "disabled",
    runlevels: list[str] | None = None,
    **_ignored,
) -> ServiceDetail:
    """Introspect one service via read-only `rc-service` sub-commands.

    ``status``/``enabled_state``/``runlevels`` are passed through from an
    already-loaded :class:`Service` so we don't re-run ``rc-status``; dependency
    metadata comes from the init script itself. OpenRC's ``ineed/iwant/iuse``
    map onto the shared model's ``requires/wants`` and ``needsme`` onto
    ``required_by``. ``**_ignored`` swallows systemd-only kwargs (e.g.
    ``sub_state``) so callers can stay init-agnostic.
    """
    run = runner or _default_runner
    wants = sorted(set(_words(run(["rc-service", name, "iwant"]))
                       + _words(run(["rc-service", name, "iuse"]))))
    return ServiceDetail(
        name=name,
        description=parse_describe(run(["rc-service", name, "describe"])),
        requires=_words(run(["rc-service", name, "ineed"])),
        wants=wants,
        after=[],  # OpenRC has no separate ordering field distinct from deps
        required_by=_words(run(["rc-service", name, "needsme"])),
        status=_norm_status(status),
        sub_state="",
        enabled_state=enabled_state,
        load_state="loaded",
        runlevels=list(runlevels or []),
    )
