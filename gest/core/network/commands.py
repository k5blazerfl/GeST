"""Pure, validated argv builder for network mutations."""

from __future__ import annotations

import re

# Interface names: letters/digits then the punctuation Linux allows
# (dots, colons, @, dashes for vlans/aliases). No spaces or shell metacharacters.
_IFACE_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._@:-]*\Z")


def valid_iface(name: str) -> bool:
    return bool(_IFACE_RE.match(name)) and len(name) <= 32


def iplink_argv(iface: str, up: bool, *, ip: str = "ip") -> list[str]:
    """Bring an interface up or down: ip link set <iface> up|down."""
    if not valid_iface(iface):
        raise ValueError(f"invalid interface: {iface!r}")
    return [ip, "link", "set", iface, "up" if up else "down"]
