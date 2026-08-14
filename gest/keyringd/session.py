"""Secret-transport sessions. Phase 2 implements only the ``plain`` algorithm,
where the secret value crosses the bus as-is; the ``dh-ietf1024-sha256-aes128-
cbc-pkcs7`` encrypted transport is Phase 3.

Pure and dependency-free: a session is just an id plus an encode/decode pair. The
registry hands out ids and looks sessions up by their object path.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(slots=True)
class PlainSession:
    """The ``plain`` algorithm: encode/decode are the identity, so a secret's
    ``value`` field is the raw bytes."""

    id: str

    def encode(self, secret: bytes) -> bytes:
        return bytes(secret)

    def decode(self, value: bytes) -> bytes:
        return bytes(value)


@dataclass
class SessionRegistry:
    """Open sessions, keyed by their object path."""

    _by_path: dict[str, PlainSession] = field(default_factory=dict)

    def open_plain(self, path_for: Callable[[str], str]) -> tuple[str, PlainSession]:
        """Create a plain session; ``path_for(id)`` yields its object path."""
        sid = secrets.token_hex(16)
        session = PlainSession(id=sid)
        path = path_for(sid)
        self._by_path[path] = session
        return path, session

    def get(self, path: str) -> PlainSession | None:
        return self._by_path.get(path)

    def close(self, path: str) -> bool:
        return self._by_path.pop(path, None) is not None
