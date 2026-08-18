"""Persist vessels under the Flotilla data dir.

Each vessel is ``<base>/<id>/`` with a ``config.json``, a ``domain.xml`` (written
on define), and (by default) a ``disk.qcow2``. Pure I/O, no libvirt. Ids are
validated to a single safe path component.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from gest.core.flotilla.model import Vessel

FLOTILLA_DIR = "~/.local/share/hede/flotilla"
_SAFE_ID = re.compile(r"\A[a-z0-9][a-z0-9_-]*\Z")


def is_safe_id(vessel_id: str) -> bool:
    return bool(_SAFE_ID.match(vessel_id)) and len(vessel_id) <= 128


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "vessel"


def vessel_dir(vessel_id: str, base: str = FLOTILLA_DIR) -> Path:
    if not is_safe_id(vessel_id):
        raise ValueError(f"unsafe vessel id {vessel_id!r}")
    return Path(base).expanduser() / vessel_id


def config_path(vessel_id: str, base: str = FLOTILLA_DIR) -> Path:
    return vessel_dir(vessel_id, base) / "config.json"


def domain_xml_path(vessel_id: str, base: str = FLOTILLA_DIR) -> Path:
    return vessel_dir(vessel_id, base) / "domain.xml"


def default_disk_path(vessel_id: str, base: str = FLOTILLA_DIR) -> Path:
    return vessel_dir(vessel_id, base) / "disk.qcow2"


def list_vessels(base: str = FLOTILLA_DIR) -> list[str]:
    root = Path(base).expanduser()
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir() if (d / "config.json").is_file())


def load_vessel(vessel_id: str, base: str = FLOTILLA_DIR) -> Vessel | None:
    try:
        return Vessel.from_dict(json.loads(config_path(vessel_id, base).read_text("utf-8")))
    except (OSError, ValueError, KeyError):
        return None


def save_vessel(vessel: Vessel, base: str = FLOTILLA_DIR) -> Path:
    path = config_path(vessel.id, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(vessel.to_dict(), fh, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def write_domain_xml(vessel_id: str, xml: str, base: str = FLOTILLA_DIR) -> Path:
    path = domain_xml_path(vessel_id, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml, encoding="utf-8")
    return path


def delete_vessel(vessel_id: str, base: str = FLOTILLA_DIR) -> bool:
    """Remove the whole vessel directory (config + xml + disk)."""
    try:
        directory = vessel_dir(vessel_id, base)
    except ValueError:
        return False
    if not directory.is_dir():
        return False
    shutil.rmtree(directory)
    return True
