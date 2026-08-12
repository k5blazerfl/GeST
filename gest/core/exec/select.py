"""Pick the executor for the current runtime — once, at startup.

The rule is deliberately simple and safe: if we're already root, run tools
in-process (polkit would only be asking whether root may act as root); otherwise
go through the polkit-gated D-Bus backend. ``GEST_EXEC=direct|dbus`` forces a
path, for testing and the rare installed-but-root case.

The euid check and the environ are injected so this is unit-testable without
actually being root.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from gest.core.exec.executor import DBusExecutor, DirectExecutor, Executor

_OVERRIDE = "GEST_EXEC"


def choose_executor(
    *,
    geteuid: Callable[[], int] | None = None,
    environ: Mapping[str, str] | None = None,
) -> Executor:
    """Return the `Executor` appropriate for how GeST is running."""
    geteuid = geteuid or os.geteuid
    environ = os.environ if environ is None else environ

    mode = environ.get(_OVERRIDE, "").strip().lower()
    if mode == "direct":
        return DirectExecutor()
    if mode == "dbus":
        return DBusExecutor()
    if mode:
        raise ValueError(f"{_OVERRIDE} must be 'direct' or 'dbus', got {mode!r}")

    return DirectExecutor() if geteuid() == 0 else DBusExecutor()
