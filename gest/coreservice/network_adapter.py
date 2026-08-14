"""Pure adapter for the Network core module — models <-> property bags.

Converters are pure (unit-testable with hand-built models); the live functions
read link status (``ip -json``, via the reader) and netifrc config
(/etc/conf.d/net). Bringing links up/down and writing netifrc are writes on the
polkit root backend, not here.
"""

from __future__ import annotations

from typing import Any

from gest.core.network import reader


def interface_to_dict(i: Any) -> dict[str, Any]:
    return {
        "name": i.name,
        "state": i.state,
        "mac": i.mac,
        "addresses": list(i.addresses),
        "up": i.up,
        "loopback": i.loopback,
    }


def config_to_dict(c: Any) -> dict[str, Any]:
    return {
        "iface": c.iface,
        "method": c.method,
        "address": c.address,
        "gateway": c.gateway,
    }


def list_interfaces() -> list[dict[str, Any]]:
    return [interface_to_dict(i) for i in reader.list_interfaces()]


def get_config(iface: str) -> dict[str, Any]:
    return config_to_dict(reader.read_interface_config(iface))
