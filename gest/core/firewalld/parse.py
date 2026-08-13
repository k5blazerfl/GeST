"""Parse firewall-cmd output. Pure; CI-testable.

firewall-cmd prints list results as a single space-separated line, so parsing
is uniform: split on whitespace. Zones/services come back unordered, so the
set-returning parsers drop ordering (a working copy diffs them as sets anyway).
"""

from __future__ import annotations


def parse_services(text: str) -> frozenset[str]:
    """The service names on a ``--list-services`` / ``--get-services`` line."""
    return frozenset(text.split())


def parse_ports(text: str) -> frozenset[str]:
    """The ``port/proto`` tokens on a ``--list-ports`` line."""
    return frozenset(text.split())


def parse_zone_list(text: str) -> list[str]:
    """The zone names on a ``--get-zones`` line, sorted for a stable display."""
    return sorted(text.split())


def parse_default_zone(text: str) -> str:
    """The single zone name from ``--get-default-zone``."""
    return text.strip()
