"""Detect the running init/service manager (systemd vs OpenRC).

GeST's HeDE stack targets systemd, but GeST-the-config-tool also runs on plain
Gentoo systems that use OpenRC. Service management (read + mutate) branches on
the init detected here so both hosts get working controls.

Detection is a cheap filesystem probe of what PID 1 exposes at runtime:
  * systemd mounts ``/run/systemd/system`` (this is what ``sd_booted(3)`` checks)
  * OpenRC populates ``/run/openrc`` once it has started

The ``GEST_INIT`` environment variable overrides the probe (values ``systemd``
or ``openrc``) — handy for tests and for driving a chroot/installer target whose
init differs from the live host.
"""

from __future__ import annotations

import os

SYSTEMD = "systemd"
OPENRC = "openrc"

_SYSTEMD_MARKER = "/run/systemd/system"
_OPENRC_MARKER = "/run/openrc"


def detect() -> str:
    """Return ``"systemd"`` or ``"openrc"`` for the running system.

    Checked fresh on every call (no caching) so a long-lived process picks up a
    ``GEST_INIT`` change and so tests can flip it without state leaking. The
    probe is a pair of ``stat`` calls — negligible cost.
    """
    override = os.environ.get("GEST_INIT", "").strip().lower()
    if override in (SYSTEMD, OPENRC):
        return override

    # A live systemd system always has this directory; prefer it when both
    # markers somehow exist (e.g. a transitioning box).
    if os.path.isdir(_SYSTEMD_MARKER):
        return SYSTEMD
    if os.path.isdir(_OPENRC_MARKER):
        return OPENRC
    # No runtime marker (early boot, unusual container): default to systemd,
    # matching the shipped HeDE stack.
    return SYSTEMD


def is_openrc() -> bool:
    return detect() == OPENRC


def is_systemd() -> bool:
    return detect() == SYSTEMD
