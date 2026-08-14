"""Keychain exception hierarchy — all vault errors derive from KeychainError."""

from __future__ import annotations


class KeychainError(Exception):
    """Base class for every keychain/vault error."""


class VaultExists(KeychainError):
    """Refused to create a vault because a file is already at the path."""


class VaultNotFound(KeychainError):
    """No vault file at the path."""


class VaultCorrupt(KeychainError):
    """The vault file is present but its envelope is malformed."""


class VaultLocked(KeychainError):
    """An operation needed the vault unlocked, but it is locked."""


class BadPassphrase(KeychainError):
    """AEAD authentication failed — a wrong passphrase or a tampered vault.

    The two are indistinguishable by design: a wrong key and a modified
    ciphertext both fail the Poly1305 tag, and that is the point (we never leak
    which). Callers surface this as "could not unlock".
    """


class UnknownCollection(KeychainError):
    """No collection with the given id (or alias)."""


class UnknownItem(KeychainError):
    """No item with the given id in the collection."""
