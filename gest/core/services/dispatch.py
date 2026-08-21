"""Init-aware read dispatch for the Services module.

Live callers (both frontends and the gestd adapter) go through here instead of
importing a reader directly, so the same code shows systemd units on a systemd
host and OpenRC services on an OpenRC host. The systemd :mod:`reader` and the
:mod:`openrc_reader` keep their own init-specific parsers and stay directly
unit-testable with injected runners; this module only chooses between them and
routes kwargs to each reader's signature.
"""

from __future__ import annotations

from collections.abc import Callable

from gest.core import init
from gest.core.services import openrc_reader, reader
from gest.core.services.model import Service, ServiceDetail

Runner = Callable[[list[str]], str]


def list_services(runner: Runner | None = None) -> list[Service]:
    if init.is_openrc():
        return openrc_reader.list_services(runner)
    return reader.list_services(runner)


def describe_service(
    name: str,
    runner: Runner | None = None,
    *,
    status: str = "inactive",
    sub_state: str = "",
    enabled_state: str = "disabled",
    runlevels: list[str] | None = None,
) -> ServiceDetail:
    if init.is_openrc():
        return openrc_reader.describe_service(
            name, runner, status=status, enabled_state=enabled_state,
            runlevels=runlevels,
        )
    return reader.describe_service(
        name, runner, status=status, sub_state=sub_state,
        enabled_state=enabled_state,
    )
