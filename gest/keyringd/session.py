"""Secret-transport sessions: the ``plain`` and ``dh-…`` algorithms.

A session encodes/decodes the ``value`` (and ``parameters``) fields of a Secret
struct. ``plain`` is the identity — the secret crosses the bus as-is. The DH
session encrypts it with AES-128-CBC under the key agreed in
:mod:`gest.keyringd.dh`, with the IV carried in ``parameters``.

The DH key agreement is pure/stdlib; only the AES transport pulls in
``cryptography`` (lazily), so importing this module never requires it.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field

from gest.keyringd import dh


@dataclass(slots=True)
class PlainSession:
    """The ``plain`` algorithm: ``value`` is the raw secret, ``parameters`` empty."""

    id: str

    def encode(self, secret: bytes) -> tuple[bytes, bytes]:
        return b"", bytes(secret)

    def decode(self, parameters: bytes, value: bytes) -> bytes:
        return bytes(value)


@dataclass(slots=True)
class DhSession:
    """The ``dh-ietf1024-sha256-aes128-cbc-pkcs7`` algorithm: ``value`` is the
    AES-128-CBC ciphertext (PKCS7-padded) and ``parameters`` is the random IV."""

    id: str
    aes_key: bytes  # 16 bytes, from dh.derive_aes_key

    def encode(self, secret: bytes) -> tuple[bytes, bytes]:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7

        iv = os.urandom(16)
        padder = PKCS7(128).padder()
        padded = padder.update(bytes(secret)) + padder.finalize()
        encryptor = Cipher(algorithms.AES(self.aes_key), modes.CBC(iv)).encryptor()
        return iv, encryptor.update(padded) + encryptor.finalize()

    def decode(self, parameters: bytes, value: bytes) -> bytes:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7

        decryptor = Cipher(algorithms.AES(self.aes_key), modes.CBC(bytes(parameters))).decryptor()
        padded = decryptor.update(bytes(value)) + decryptor.finalize()
        unpadder = PKCS7(128).unpadder()
        return unpadder.update(padded) + unpadder.finalize()


@dataclass
class SessionRegistry:
    """Open sessions, keyed by their object path."""

    _by_path: dict = field(default_factory=dict)

    def open_plain(self, path_for: Callable[[str], str]) -> tuple[str, PlainSession]:
        """Create a plain session; ``path_for(id)`` yields its object path."""
        sid = secrets.token_hex(16)
        session = PlainSession(id=sid)
        path = path_for(sid)
        self._by_path[path] = session
        return path, session

    def open_dh(self, client_public: bytes,
                path_for: Callable[[str], str]) -> tuple[str, bytes, DhSession]:
        """Agree a key with the client's public key and open a DH session.
        Returns ``(path, server_public_key, session)``."""
        private, server_public = dh.generate_keypair()
        aes_key = dh.derive_aes_key(dh.shared_secret(private, client_public))
        sid = secrets.token_hex(16)
        session = DhSession(id=sid, aes_key=aes_key)
        path = path_for(sid)
        self._by_path[path] = session
        return path, server_public, session

    def get(self, path: str):
        return self._by_path.get(path)

    def close(self, path: str) -> bool:
        return self._by_path.pop(path, None) is not None
