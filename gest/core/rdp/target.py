"""Resolve a ``.rdp`` file or ``rdp://`` URI to a transient :class:`RdpProfile`.

This is what lets a ``.rdp`` handed to Gangway by the desktop — double-clicked, or
opened via the Customs MIME/URI handler — be launched **ad-hoc**, without first
saving it as a named profile. URI/file parsing is pure; only
:func:`profile_from_file` touches disk (it reads the file).
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from gest.core.rdp import rdpfile
from gest.core.rdp.model import RdpProfile


def is_uri(target: str) -> bool:
    return target.startswith("rdp://")


def profile_from_uri(uri: str) -> RdpProfile:
    """``rdp://[user@]host[:port]`` → a transient profile (other fields default)."""
    parsed = urlparse(uri)
    try:
        port = parsed.port or 3389
    except ValueError:
        port = 3389
    host = parsed.hostname or ""
    return RdpProfile(name=host or "rdp", host=host, port=port,
                      username=unquote(parsed.username) if parsed.username else "")


def local_path(target: str) -> str:
    """A ``file://`` URL → a filesystem path; anything else is returned as-is."""
    if target.startswith("file://"):
        return unquote(urlparse(target).path)
    return target


def profile_from_file(path: str) -> RdpProfile:
    resolved = Path(local_path(path)).expanduser()
    return rdpfile.parse(resolved.read_text(encoding="utf-8"), resolved.stem or "rdp")


def profile_from_target(target: str) -> RdpProfile:
    """A ``.rdp`` path, a ``file://`` URL, or an ``rdp://`` URI → a profile."""
    if is_uri(target):
        return profile_from_uri(target)
    return profile_from_file(target)
