"""Persist bottles under the Drydock data dir.

Each bottle is ``<base>/<id>/`` with a ``config.json`` and (by default) a
``prefix/`` WINEPREFIX. A user action, no polkit. Ids are validated to a single
safe path component.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from gest.core.drydock.model import Bottle

DRYDOCK_DIR = "~/.local/share/hede/drydock"
_SAFE_ID = re.compile(r"\A[a-z0-9][a-z0-9_-]*\Z")


def is_safe_id(bottle_id: str) -> bool:
    return bool(_SAFE_ID.match(bottle_id)) and len(bottle_id) <= 128


def slug(name: str) -> str:
    """Derive a safe bottle id from a display name."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "bottle"


def bottle_dir(bottle_id: str, base: str = DRYDOCK_DIR) -> Path:
    if not is_safe_id(bottle_id):
        raise ValueError(f"unsafe bottle id {bottle_id!r}")
    return Path(base).expanduser() / bottle_id


def config_path(bottle_id: str, base: str = DRYDOCK_DIR) -> Path:
    return bottle_dir(bottle_id, base) / "config.json"


def default_prefix(bottle_id: str, base: str = DRYDOCK_DIR) -> Path:
    return bottle_dir(bottle_id, base) / "prefix"


def list_bottles(base: str = DRYDOCK_DIR) -> list[str]:
    root = Path(base).expanduser()
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir() if (d / "config.json").is_file())


def load_bottle(bottle_id: str, base: str = DRYDOCK_DIR) -> Bottle | None:
    try:
        return Bottle.from_dict(json.loads(config_path(bottle_id, base).read_text("utf-8")))
    except (OSError, ValueError, KeyError):
        return None


def save_bottle(bottle: Bottle, base: str = DRYDOCK_DIR) -> Path:
    if not bottle.prefix:
        bottle.prefix = str(default_prefix(bottle.id, base))
    path = config_path(bottle.id, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(bottle.to_dict(), fh, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def delete_bottle(bottle_id: str, base: str = DRYDOCK_DIR) -> bool:
    """Remove the whole bottle directory (config + prefix)."""
    try:
        directory = bottle_dir(bottle_id, base)
    except ValueError:
        return False
    if not directory.is_dir():
        return False
    shutil.rmtree(directory)
    return True
