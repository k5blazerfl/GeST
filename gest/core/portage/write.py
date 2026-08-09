"""The :class:`ConfigWrite` value type and the path allow-list check.

The core produces one or more :class:`ConfigWrite`\\ s describing *what file
should contain what text*; the privileged backend applies them atomically. The
frontend is untrusted, so :func:`is_within_etc_portage` is a first-pass guard
that the backend MUST re-run after ``realpath`` to defeat symlink escapes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ConfigWrite:
    """A pending write of ``text`` to ``path`` (``text == ""`` deletes the file)."""

    path: str
    text: str
    mode: int = 0o644


def etc_portage_dir(root: str = "/") -> str:
    return os.path.normpath(os.path.join(root, "etc", "portage"))


def is_within_etc_portage(path: str, root: str = "/") -> bool:
    """True if ``path`` normalises to a location inside ``<root>/etc/portage/``.

    Pure ``normpath`` check that rejects ``..`` traversal. It does NOT resolve
    symlinks — the backend must additionally ``realpath`` before writing.
    """
    base = etc_portage_dir(root)
    norm = os.path.normpath(path)
    return norm == base or norm.startswith(base + os.sep)
