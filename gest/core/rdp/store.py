"""Persist RDP profiles as ``.rdp`` files under the Gangway config dir.

A user action, no polkit: profiles live in ``$XDG_CONFIG_HOME/hede/gangway/`` as
plain ``.rdp`` files (so they interoperate with Windows and the ``.rdp`` MIME
handler). Names are validated to stay a single safe filename component.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from gest.core.rdp import rdpfile
from gest.core.rdp.model import RdpProfile

GANGWAY_DIR = "~/.config/hede/gangway"
_SAFE_NAME = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9 _.-]*\Z")


def is_safe_name(name: str) -> bool:
    return bool(_SAFE_NAME.match(name)) and "/" not in name and len(name) <= 128


def profile_path(name: str, base: str = GANGWAY_DIR) -> Path:
    if not is_safe_name(name):
        raise ValueError(f"unsafe profile name {name!r}")
    return Path(base).expanduser() / f"{name}.rdp"


def list_profiles(base: str = GANGWAY_DIR) -> list[str]:
    directory = Path(base).expanduser()
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.rdp"))


def load_profile(name: str, base: str = GANGWAY_DIR) -> RdpProfile | None:
    path = profile_path(name, base)
    try:
        return rdpfile.parse(path.read_text(encoding="utf-8"), name)
    except OSError:
        return None


def save_profile(profile: RdpProfile, base: str = GANGWAY_DIR) -> Path:
    path = profile_path(profile.name, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(rdpfile.render(profile))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def delete_profile(name: str, base: str = GANGWAY_DIR) -> bool:
    try:
        profile_path(name, base).unlink()
        return True
    except (FileNotFoundError, ValueError):
        return False
