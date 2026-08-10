"""GeST's own record of which repositories to sync when Software Management opens.

The selection is a plain newline list of repository names in a GeST-owned state
file (``/etc/portage/gest/refresh``) — deliberately *not* in ``repos.conf``, so
``eselect``'s rewrites and Portage's parser never touch it. This module is the
pure parse/render codec; the reader reads the file, and writes go through the
Portage ``WriteConfig`` RPC (see :mod:`gest.core.repos.writer`).
"""

from __future__ import annotations

from gest.core.portage import paths

STATE_NAME = "refresh"


def state_path(root: str | None = None) -> str:
    """The refresh-state file path, ``/etc/portage/gest/refresh``."""
    return paths.gest_state(STATE_NAME, root)


def parse(text: str) -> set[str]:
    """Repository names listed in the state file (blank/``#`` lines ignored)."""
    names: set[str] = set()
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            names.add(s)
    return names


def render(names: set[str]) -> str:
    """Render a name set to file text (sorted, one per line).

    An empty set renders to ``""`` so the write deletes the file rather than
    leaving an empty fragment behind.
    """
    lines = sorted(names)
    return "\n".join(lines) + "\n" if lines else ""


def toggle(names: set[str], name: str, on: bool) -> set[str]:
    """Return ``names`` with ``name`` added (``on``) or removed."""
    out = set(names)
    out.add(name) if on else out.discard(name)
    return out
