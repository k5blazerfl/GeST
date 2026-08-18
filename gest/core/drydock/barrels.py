"""Persist barrels under the Drydock data dir.

Each barrel is ``<base>/<id>/`` with a ``config.json`` and (by default) a
``prefix/`` WINEPREFIX. A user action, no polkit. Ids are validated to a single
safe path component.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from gest.core.drydock.model import Barrel

DRYDOCK_DIR = "~/.local/share/hede/drydock"
_SAFE_ID = re.compile(r"\A[a-z0-9][a-z0-9_-]*\Z")


def is_safe_id(barrel_id: str) -> bool:
    return bool(_SAFE_ID.match(barrel_id)) and len(barrel_id) <= 128


def slug(name: str) -> str:
    """Derive a safe barrel id from a display name."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "barrel"


def barrel_dir(barrel_id: str, base: str = DRYDOCK_DIR) -> Path:
    if not is_safe_id(barrel_id):
        raise ValueError(f"unsafe barrel id {barrel_id!r}")
    return Path(base).expanduser() / barrel_id


def config_path(barrel_id: str, base: str = DRYDOCK_DIR) -> Path:
    return barrel_dir(barrel_id, base) / "config.json"


def default_prefix(barrel_id: str, base: str = DRYDOCK_DIR) -> Path:
    return barrel_dir(barrel_id, base) / "prefix"


def list_barrels(base: str = DRYDOCK_DIR) -> list[str]:
    root = Path(base).expanduser()
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir() if (d / "config.json").is_file())


def load_barrel(barrel_id: str, base: str = DRYDOCK_DIR) -> Barrel | None:
    try:
        return Barrel.from_dict(json.loads(config_path(barrel_id, base).read_text("utf-8")))
    except (OSError, ValueError, KeyError):
        return None


def save_barrel(barrel: Barrel, base: str = DRYDOCK_DIR) -> Path:
    if not barrel.prefix:
        barrel.prefix = str(default_prefix(barrel.id, base))
    path = config_path(barrel.id, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(barrel.to_dict(), fh, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def delete_barrel(barrel_id: str, base: str = DRYDOCK_DIR) -> bool:
    """Remove the whole barrel directory (config + prefix)."""
    try:
        directory = barrel_dir(barrel_id, base)
    except ValueError:
        return False
    if not directory.is_dir():
        return False
    shutil.rmtree(directory)
    return True
