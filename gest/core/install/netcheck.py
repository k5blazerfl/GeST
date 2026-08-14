"""Connectivity pre-flight for the installer.

The install downloads a stage3 and emerges packages, so it needs the *live*
environment to be online. This checks reachability of the Gentoo mirror before a
run starts, so an offline machine gets a clear "connect first" message instead of
a confusing stage3-download failure five steps in.

Kept tiny and injectable: the URL opener is a parameter, so the check is unit-
testable (a fake opener that returns a status or raises) without real network.
"""

from __future__ import annotations

import urllib.request
from collections.abc import Callable

from gest.core.stage3 import index

# A cheap, always-present path on the mirror to probe.
DEFAULT_PROBE = index.MIRROR.rstrip("/") + "/releases/"

Opener = Callable[..., object]


def check_connectivity(
    *, probe_url: str = DEFAULT_PROBE,
    opener: Opener = urllib.request.urlopen,
    timeout: int = 8,
) -> tuple[bool, str]:
    """Return ``(online, detail)`` for whether the mirror is reachable.

    ``online`` is True on an HTTP status < 400. ``opener`` is injected so tests can
    supply a fake (an object with a ``status``/``code`` and context-manager
    protocol, or one that raises). Any exception → offline with the reason.
    """
    try:
        with opener(probe_url, timeout=timeout) as resp:
            code = getattr(resp, "status", None) or getattr(resp, "code", 200)
            ok = 200 <= int(code) < 400
            return ok, f"{probe_url} → HTTP {code}"
    except Exception as exc:
        return False, f"{probe_url}: {exc}"
