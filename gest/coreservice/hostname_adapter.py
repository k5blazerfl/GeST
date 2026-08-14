"""Pure adapter for the Hostname core module — ``core`` <-> plain data.

No D-Bus import: this is the contract logic, unit-testable without a bus. The
D-Bus object in ``hostname.py`` wraps these, doing only variant packing.
"""

from __future__ import annotations

from gest.core.system import hostname as core


def get_state() -> dict[str, str]:
    """The Hostname module's current state (the property bag for GetState)."""
    return {"hostname": core.current_hostname()}


def validate(name: str) -> tuple[bool, str]:
    """(ok, message) for a candidate hostname."""
    if core.valid_hostname(name):
        return True, ""
    return False, "invalid hostname (RFC 1123 labels, ≤253 chars)"


def render(name: str) -> str:
    """The /etc/conf.d/hostname text a write would produce (a preview)."""
    return core.render_conf(name)
