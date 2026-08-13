"""Read firewalld's permanent config unprivileged, via an injectable runner.

``firewall-cmd --permanent --list-*`` is readable without privilege on typical
setups, so the TUI can show the current allowances without a polkit prompt;
mutating them goes through the polkit-gated backend. Every read is best-effort:
a failing call yields empties rather than raising, so an unusual/locked-down
host still opens the module (just with nothing to show).
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from gest.core.firewalld import commands, parse
from gest.core.firewalld.model import ZoneConfig

Runner = Callable[[list[str]], tuple[int, str]]


def _default_runner(argv: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True)
        return proc.returncode, proc.stdout
    except OSError:
        return 127, ""


def firewalld_available(runner: Runner | None = None) -> bool:
    """True when firewall-cmd answers ``--get-default-zone`` (daemon reachable)."""
    run = runner or _default_runner
    code, _out = run(commands.get_default_zone_argv())
    return code == 0


def default_zone(runner: Runner | None = None) -> str:
    """The configured default zone name, or "" if firewalld is unreachable."""
    run = runner or _default_runner
    code, out = run(commands.get_default_zone_argv())
    return parse.parse_default_zone(out) if code == 0 else ""


def zone_config(zone: str, runner: Runner | None = None) -> ZoneConfig:
    """The permanent services + ports of ``zone`` (empties on any read failure)."""
    if not commands.valid_zone(zone):
        return ZoneConfig(zone=zone)
    run = runner or _default_runner
    code, out = run(commands.list_services_argv(zone))
    services = parse.parse_services(out) if code == 0 else frozenset()
    code, out = run(commands.list_ports_argv(zone))
    ports = parse.parse_ports(out) if code == 0 else frozenset()
    return ZoneConfig(zone=zone, services=services, ports=ports)


def known_services(runner: Runner | None = None) -> frozenset[str]:
    """Every service name firewalld knows about (for the add-service picker)."""
    run = runner or _default_runner
    code, out = run(commands.get_services_argv())
    return parse.parse_services(out) if code == 0 else frozenset()
