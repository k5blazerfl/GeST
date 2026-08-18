"""Persist the Customs :class:`~gest.core.customs.identity.IdentityMap`.

This JSON file is the **source of truth HeDE's foreign-toplevel taskbar reads**
to map a running window's ``WM_CLASS``/``app_id`` back to its synthesized
``.desktop`` (so it shows the right icon/title instead of a generic blob). Both
Drydock and Gangway write it, so it lives at a shared Customs path rather than
under either subsystem.

Atomic 0644 writes, mirroring :func:`gest.core.customs.desktop.write_entry`. The
:func:`register_entry`/:func:`unregister_entry` helpers do a load-modify-save so
callers needn't hold the map.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from gest.core.customs.identity import IdentityMap

CUSTOMS_DIR = "~/.local/share/hede/customs"
IDENTITY_FILE = "identity.json"


def default_path() -> str:
    return str(Path(CUSTOMS_DIR).expanduser() / IDENTITY_FILE)


def _resolve(path: str | None) -> Path:
    return Path(path or default_path()).expanduser()


def load(path: str | None = None) -> IdentityMap:
    """Load the map, or an empty one if it is missing/unreadable/corrupt."""
    try:
        data = json.loads(_resolve(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return IdentityMap()
    return IdentityMap.from_dict(data)


def save(identity: IdentityMap, path: str | None = None) -> Path:
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(identity.to_dict(), fh, indent=2, sort_keys=True)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return target


def register_entry(keys: list[str], desktop_id: str, path: str | None = None) -> Path:
    """Point ``keys`` (WM_CLASS/app_id) at ``desktop_id`` and persist."""
    identity = load(path)
    identity.register(keys, desktop_id)
    return save(identity, path)


def unregister_entry(desktop_id: str, path: str | None = None) -> Path:
    """Drop every key pointing at ``desktop_id`` and persist."""
    identity = load(path)
    identity.unregister(desktop_id)
    return save(identity, path)
