"""The vault's seal/unseal layer — borrowed primitives only, no custom crypto.

Key derivation is **Argon2id** and authenticated encryption is
**ChaCha20-Poly1305**, both from the audited ``cryptography`` library (added to
GeST's optional ``keychain`` dependency set). Per ``docs/design/keychain.md`` we
own a vault *format*, never an algorithm.

This is the only module in the package that imports ``cryptography``; keeping it
thin means the pure model layer (and its tests) never pulls the dependency in.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from gest.core.keychain.errors import BadPassphrase

# ``cryptography`` is imported lazily inside the functions that use it, so merely
# importing this module (e.g. for the KdfParams dataclass, or by the vault for
# type references) does not require the optional dependency to be installed. The
# import only bites when a seal/unseal/derive is actually performed.

KEY_LEN = 32  # ChaCha20-Poly1305 key size
NONCE_LEN = 12  # ChaCha20-Poly1305 (IETF) nonce size
SALT_LEN = 16

# Argon2id defaults: OWASP-ish interactive parameters. Tunable per-vault so a
# slow machine can dial down and a server can dial up, and so tests run fast.
DEFAULT_TIME_COST = 3
DEFAULT_MEMORY_COST_KIB = 64 * 1024  # 64 MiB
DEFAULT_PARALLELISM = 4


@dataclass(frozen=True, slots=True)
class KdfParams:
    """Argon2id parameters, stored (minus the derived key) in the vault header so
    the same passphrase re-derives the same key on the next unlock."""

    salt: bytes
    time_cost: int = DEFAULT_TIME_COST
    memory_cost: int = DEFAULT_MEMORY_COST_KIB  # KiB
    parallelism: int = DEFAULT_PARALLELISM
    length: int = KEY_LEN

    @classmethod
    def generate(cls, **overrides) -> KdfParams:
        """Fresh params with a random salt (overrides let tests pick cheap
        costs)."""
        return cls(salt=os.urandom(SALT_LEN), **overrides)

    def to_dict(self) -> dict:
        return {
            "algo": "argon2id",
            "salt": b64(self.salt),
            "time_cost": self.time_cost,
            "memory_cost": self.memory_cost,
            "parallelism": self.parallelism,
            "length": self.length,
        }

    @classmethod
    def from_dict(cls, d: dict) -> KdfParams:
        if d.get("algo") != "argon2id":
            raise ValueError(f"unsupported KDF {d.get('algo')!r}")
        return cls(
            salt=unb64(d["salt"]),
            time_cost=int(d["time_cost"]),
            memory_cost=int(d["memory_cost"]),
            parallelism=int(d["parallelism"]),
            length=int(d.get("length", KEY_LEN)),
        )


def derive_key(passphrase: str, params: KdfParams) -> bytes:
    """Argon2id(passphrase, salt) → a ``params.length``-byte key."""
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

    kdf = Argon2id(
        salt=params.salt,
        length=params.length,
        iterations=params.time_cost,
        lanes=params.parallelism,
        memory_cost=params.memory_cost,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def seal(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """AEAD-encrypt ``plaintext`` under ``key`` with a fresh random nonce.

    Returns ``nonce || ciphertext``. ``aad`` binds unencrypted context (the
    vault header) to the ciphertext so it cannot be swapped underneath us.
    """
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

    nonce = os.urandom(NONCE_LEN)
    ct = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)
    return nonce + ct


def unseal(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    """Reverse :func:`seal`. Raises :class:`BadPassphrase` if authentication
    fails — a wrong key or a tampered vault, deliberately indistinguishable."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

    if len(blob) < NONCE_LEN:
        raise BadPassphrase("vault ciphertext too short")
    nonce, ct = blob[:NONCE_LEN], blob[NONCE_LEN:]
    try:
        return ChaCha20Poly1305(key).decrypt(nonce, ct, aad)
    except InvalidTag as exc:
        raise BadPassphrase(
            "vault authentication failed (wrong passphrase or tampered vault)"
        ) from exc


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def unb64(text: str) -> bytes:
    return base64.b64decode(text)
