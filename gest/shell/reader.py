"""Pure read helpers behind the shell service (injectable for tests).

Kept free of Portage and dbus-next imports at module load: the heavy ``core``
reader is imported lazily so these functions can be unit-tested with a fake.
"""

from __future__ import annotations

from collections.abc import Callable


def update_count(list_upgradable: Callable[[], list] | None = None) -> int:
    """Number of installed packages with a newer version available.

    Uses the in-process Portage reader (fast, no root, no ``emerge``). Pass
    ``list_upgradable`` to inject a fake in tests.
    """
    if list_upgradable is None:
        from gest.core.software import reader as sw

        list_upgradable = sw.list_upgradable
    return len(list_upgradable())
