"""Pure argv builders + input validators for the firewall-cmd tool.

No I/O; CI-testable. Every mutating/listing command is built at the *permanent*
scope so changes survive a reload/reboot; :func:`reload_argv` then applies the
permanent config to the live runtime. Builders that take user input validate it
and raise ``ValueError`` on bad values, so no unchecked string ever reaches
``firewall-cmd`` (the backend re-validates server-side regardless).
"""

from __future__ import annotations

import re

# A conservative firewalld zone name: letters, digits, underscore and dash.
_ZONE_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
# A firewalld service name: lowercase letters/digits, dashes (e.g. ssh, dhcpv6-client).
_SERVICE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# A port allowance: "<number>/tcp" or "<number>/udp".
_PORT_RE = re.compile(r"^(\d{1,5})/(tcp|udp)$")


def valid_zone(zone: str) -> bool:
    return bool(_ZONE_RE.match(zone or ""))


def valid_service(service: str) -> bool:
    return bool(_SERVICE_RE.match(service or ""))


def valid_port(port: str) -> bool:
    match = _PORT_RE.match(port or "")
    return bool(match) and 1 <= int(match.group(1)) <= 65535


def _require_zone(zone: str) -> None:
    if not valid_zone(zone):
        raise ValueError(f"invalid firewalld zone name: {zone!r}")


def _require_service(service: str) -> None:
    if not valid_service(service):
        raise ValueError(f"invalid firewalld service name: {service!r}")


def _require_port(port: str) -> None:
    if not valid_port(port):
        raise ValueError(f"invalid port (expected N/tcp or N/udp, 1-65535): {port!r}")


def get_default_zone_argv(firewall_cmd: str = "firewall-cmd") -> list[str]:
    return [firewall_cmd, "--get-default-zone"]


def list_all_zones_argv(firewall_cmd: str = "firewall-cmd") -> list[str]:
    """List every defined zone name (space-separated)."""
    return [firewall_cmd, "--get-zones"]


def get_services_argv(firewall_cmd: str = "firewall-cmd") -> list[str]:
    """List every known service name (for the add-service picker)."""
    return [firewall_cmd, "--get-services"]


def list_services_argv(zone: str, firewall_cmd: str = "firewall-cmd") -> list[str]:
    _require_zone(zone)
    return [firewall_cmd, "--permanent", "--zone", zone, "--list-services"]


def list_ports_argv(zone: str, firewall_cmd: str = "firewall-cmd") -> list[str]:
    _require_zone(zone)
    return [firewall_cmd, "--permanent", "--zone", zone, "--list-ports"]


def add_service_argv(zone: str, service: str,
                     firewall_cmd: str = "firewall-cmd") -> list[str]:
    _require_zone(zone)
    _require_service(service)
    return [firewall_cmd, "--permanent", "--zone", zone, "--add-service", service]


def remove_service_argv(zone: str, service: str,
                        firewall_cmd: str = "firewall-cmd") -> list[str]:
    _require_zone(zone)
    _require_service(service)
    return [firewall_cmd, "--permanent", "--zone", zone, "--remove-service", service]


def add_port_argv(zone: str, port: str,
                  firewall_cmd: str = "firewall-cmd") -> list[str]:
    _require_zone(zone)
    _require_port(port)
    return [firewall_cmd, "--permanent", "--zone", zone, "--add-port", port]


def remove_port_argv(zone: str, port: str,
                     firewall_cmd: str = "firewall-cmd") -> list[str]:
    _require_zone(zone)
    _require_port(port)
    return [firewall_cmd, "--permanent", "--zone", zone, "--remove-port", port]


def reload_argv(firewall_cmd: str = "firewall-cmd") -> list[str]:
    """Apply the permanent config to the live runtime (``firewall-cmd --reload``)."""
    return [firewall_cmd, "--reload"]
