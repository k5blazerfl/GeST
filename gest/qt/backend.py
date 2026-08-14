"""Shared bridge from a PySide slot to an async, polkit-gated core backend.

Runs the coroutine in a short-lived asyncio loop and normalises the common
[ok, output] return into (ok, message); any error becomes (False, str(e)).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


def run_backend(coro_factory: Callable[[], Any]) -> tuple[bool, str]:
    try:
        result = asyncio.run(coro_factory())
        if isinstance(result, (list, tuple)) and result:
            return (bool(result[0]), str(result[1]) if len(result) > 1 else "")
        return (True, "")
    except Exception as e:  # surface backend/D-Bus/polkit errors to the UI
        return (False, str(e))
