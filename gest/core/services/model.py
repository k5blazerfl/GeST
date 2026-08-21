"""Data type for a system service (frontend-agnostic).

One shape spans both init systems. Under systemd a Service carries its runtime
``ActiveState`` (active / inactive / failed / activating / …) and its install
state from ``systemctl is-enabled`` (enabled / disabled / static / masked / …).
The OpenRC reader normalizes onto the same vocabulary (started→active,
stopped→inactive, crashed→failed; enabled_state is enabled/disabled) and fills
``runlevels`` with the runlevels the service is added to — empty under systemd.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# is-enabled / UnitFileState values that mean "starts at boot" for the toggle.
_ENABLED_AT_BOOT = ("enabled", "enabled-runtime")


@dataclass(slots=True)
class Service:
    name: str                          # unit name, e.g. "sshd.service"
    status: str = "inactive"           # ActiveState: active/inactive/failed/activating/…
    sub_state: str = ""                # SubState: running/exited/dead/failed/…
    enabled_state: str = "disabled"    # systemctl is-enabled: enabled/disabled/static/masked/…
    description: str = ""
    runlevels: list[str] = field(default_factory=list)  # OpenRC only; [] under systemd

    @property
    def enabled(self) -> bool:
        """Starts at boot (the enable toggle's notion)."""
        return self.enabled_state in _ENABLED_AT_BOOT

    @property
    def running(self) -> bool:
        return self.status == "active"

    @property
    def masked(self) -> bool:
        return self.enabled_state.startswith("masked")

    @property
    def static(self) -> bool:
        return self.enabled_state == "static"


@dataclass(slots=True)
class ServiceDetail:
    """Introspected detail for one service (read-only, from ``systemctl show``)."""

    name: str
    description: str = ""
    requires: list[str] = field(default_factory=list)     # Requires=
    wants: list[str] = field(default_factory=list)        # Wants=
    after: list[str] = field(default_factory=list)        # After= (ordering)
    required_by: list[str] = field(default_factory=list)  # reverse: RequiredBy= + WantedBy=
    status: str = "inactive"
    sub_state: str = ""
    enabled_state: str = "disabled"
    load_state: str = ""                                  # loaded / not-found / masked
    runlevels: list[str] = field(default_factory=list)   # OpenRC only; [] under systemd

    @property
    def running(self) -> bool:
        return self.status == "active"

    @property
    def enabled(self) -> bool:
        return self.enabled_state in _ENABLED_AT_BOOT

    @property
    def masked(self) -> bool:
        return self.enabled_state.startswith("masked")
