"""Pure object-path codec: vault ids ↔ Secret Service D-Bus object paths.

A D-Bus object-path element may contain only ``[A-Za-z0-9_]``. Vault ids are hex
(``secrets.token_hex``) and collection aliases are lowercase words, so both are
already path-safe; every id is nonetheless validated on the way in and out, and
malformed paths decode to ``None`` rather than raising, so a hostile client can't
crash the daemon with a crafted path.
"""

from __future__ import annotations

import re

from gest.keyringd import contract

_SAFE = re.compile(r"\A[A-Za-z0-9_]+\Z")


def _safe(element: str) -> bool:
    return bool(_SAFE.match(element))


def collection_path(collection_id: str) -> str:
    if not _safe(collection_id):
        raise ValueError(f"unsafe collection id {collection_id!r}")
    return f"{contract.COLLECTION_BASE}/{collection_id}"


def item_path(collection_id: str, item_id: str) -> str:
    if not (_safe(collection_id) and _safe(item_id)):
        raise ValueError(f"unsafe id in ({collection_id!r}, {item_id!r})")
    return f"{contract.COLLECTION_BASE}/{collection_id}/{item_id}"


def session_path(session_id: str) -> str:
    if not _safe(session_id):
        raise ValueError(f"unsafe session id {session_id!r}")
    return f"{contract.SESSION_BASE}/{session_id}"


def alias_path(alias: str) -> str:
    if not _safe(alias):
        raise ValueError(f"unsafe alias {alias!r}")
    return f"{contract.ALIAS_BASE}/{alias}"


def parse_collection_path(path: str) -> str | None:
    """``…/collection/<cid>`` → ``cid`` (not an item path), else ``None``."""
    prefix = contract.COLLECTION_BASE + "/"
    if not path.startswith(prefix):
        return None
    rest = path[len(prefix):]
    return rest if "/" not in rest and _safe(rest) else None


def parse_item_path(path: str) -> tuple[str, str] | None:
    """``…/collection/<cid>/<iid>`` → ``(cid, iid)``, else ``None``."""
    prefix = contract.COLLECTION_BASE + "/"
    if not path.startswith(prefix):
        return None
    parts = path[len(prefix):].split("/")
    if len(parts) != 2 or not all(_safe(p) for p in parts):
        return None
    return parts[0], parts[1]
