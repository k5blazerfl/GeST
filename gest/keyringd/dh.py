"""Diffie-Hellman key agreement for the Secret Service encrypted transport.

The ``dh-ietf1024-sha256-aes128-cbc-pkcs7`` algorithm agrees a shared secret over
the IETF 1024-bit MODP group (RFC 2409 "Second Oakley Group"), then derives a
128-bit AES key with HKDF-SHA256 (null salt, empty info) — exactly what libsecret
and gnome-keyring do, so an unmodified client interoperates.

This module is pure and stdlib-only (big-int ``pow`` + ``hmac``/``hashlib`` HKDF);
the AES-CBC transport that *uses* the derived key lives in
:class:`gest.keyringd.session.DhSession` (which pulls in ``cryptography`` lazily).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# RFC 2409 Second Oakley Group (1024-bit MODP), generator 2.
PRIME = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE65381"
    "FFFFFFFFFFFFFFFF",
    16,
)
GENERATOR = 2
KEY_BYTES = PRIME.bit_length() // 8  # 128 — the fixed width of public keys / shared secret


def generate_keypair() -> tuple[int, bytes]:
    """A private exponent and its public key as a fixed-width 128-byte string."""
    private = secrets.randbelow(PRIME - 3) + 2
    public = pow(GENERATOR, private, PRIME)
    return private, public.to_bytes(KEY_BYTES, "big")


def shared_secret(private: int, peer_public: bytes) -> bytes:
    """The DH shared secret as a fixed-width 128-byte string (left-zero-padded)."""
    peer = int.from_bytes(peer_public, "big")
    return pow(peer, private, PRIME).to_bytes(KEY_BYTES, "big")


def derive_aes_key(shared: bytes) -> bytes:
    """HKDF-SHA256 of the shared secret → a 16-byte AES-128 key (null salt, no
    info), per the Secret Service spec."""
    return _hkdf_sha256(shared, info=b"", length=16)


def _hkdf_sha256(ikm: bytes, info: bytes, length: int) -> bytes:
    hash_len = hashlib.sha256().digest_size
    salt = b"\x00" * hash_len  # RFC 5869: absent salt is HashLen zero bytes
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    okm = b""
    block = b""
    counter = 1
    while len(okm) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        okm += block
        counter += 1
    return okm[:length]
