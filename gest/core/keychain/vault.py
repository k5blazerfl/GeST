"""The encrypted vault — file envelope, unlock/lock lifecycle, persistence.

On disk the vault is a small JSON *envelope* wrapping an opaque AEAD blob::

    {
      "format": "gest-keyring",
      "version": 1,
      "kdf": {"algo": "argon2id", "salt": "...", "time_cost": 3, ...},
      "cipher": "chacha20poly1305",
      "blob": "<base64 nonce||ciphertext>"
    }

The header (everything but ``blob``) is fed to the AEAD as additional data, so
the KDF parameters and version are authenticated — an attacker cannot downgrade
``time_cost`` or swap the salt without invalidating the tag.

Unlocked, the vault holds the derived key and the decrypted
:class:`~gest.core.keychain.model.VaultPayload` in memory; mutations happen there
and are flushed with :meth:`save`. Locking drops both.

This wholesale-encrypt design (the entire payload sealed as one blob, re-sealed
with a fresh nonce on every save) mirrors how KeePass/KDBX decrypts the whole
database on unlock; per-item key wrapping is a later refinement, not needed for
correctness here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from gest.core.keychain import crypto
from gest.core.keychain.crypto import KdfParams
from gest.core.keychain.errors import (
    BadPassphrase,
    UnknownCollection,
    VaultCorrupt,
    VaultExists,
    VaultLocked,
    VaultNotFound,
)
from gest.core.keychain.model import FORMAT, Item, VaultPayload

CIPHER = "chacha20poly1305"
ENVELOPE_VERSION = 1

# Default location; a real deployment points HeDE at $XDG_DATA_HOME/hede/keyring/.
DEFAULT_VAULT_PATH = "~/.local/share/hede/keyring/default.vault"


class Vault:
    """An on-disk encrypted secrets store. Construct, then :meth:`create` or
    :meth:`unlock`; mutate through the delegating methods; :meth:`save`; and
    :meth:`lock` when done."""

    def __init__(self, path: str | os.PathLike) -> None:
        self.path = Path(path).expanduser()
        self._key: bytes | None = None
        self._payload: VaultPayload | None = None
        self._kdf: KdfParams | None = None

    # ---- lifecycle -----------------------------------------------------
    @property
    def is_locked(self) -> bool:
        return self._key is None

    def exists(self) -> bool:
        return self.path.exists()

    @classmethod
    def create(
        cls,
        path: str | os.PathLike,
        passphrase: str,
        *,
        kdf_params: KdfParams | None = None,
    ) -> Vault:
        """Create a new vault seeded with the default ``login`` collection and
        return it **unlocked**. Refuses to clobber an existing file."""
        vault = cls(path)
        if vault.exists():
            raise VaultExists(f"a vault already exists at {vault.path}")
        vault._kdf = kdf_params or KdfParams.generate()
        vault._key = crypto.derive_key(passphrase, vault._kdf)
        vault._payload = VaultPayload.new_default()
        vault.save()
        return vault

    def unlock(self, passphrase: str) -> None:
        """Read the envelope, derive the key from the stored KDF params, and
        decrypt. Raises :class:`BadPassphrase` on a wrong passphrase or tamper."""
        if not self.exists():
            raise VaultNotFound(f"no vault at {self.path}")
        header, blob = self._read_envelope()
        kdf = KdfParams.from_dict(header["kdf"])
        key = crypto.derive_key(passphrase, kdf)
        plaintext = crypto.unseal(key, blob, aad=_aad(header))
        try:
            payload = VaultPayload.from_dict(json.loads(plaintext))
        except (ValueError, json.JSONDecodeError) as exc:
            # Auth passed but contents don't parse — genuine corruption, not a
            # wrong passphrase.
            raise VaultCorrupt(f"decrypted payload is not valid: {exc}") from exc
        self._kdf, self._key, self._payload = kdf, key, payload

    def lock(self) -> None:
        """Drop the key and decrypted payload. Python can't guarantee the bytes
        are wiped from memory (immutable ``bytes``, GC), but we release every
        reference we hold; true zeroization is a hardening item for a compiled
        daemon."""
        self._key = None
        self._payload = None
        # keep self._kdf so a re-unlock reuses params without a re-read

    def change_passphrase(
        self, new_passphrase: str, *, kdf_params: KdfParams | None = None
    ) -> None:
        """Re-key the vault to ``new_passphrase`` (with a fresh salt by default)
        and persist. Requires the vault to be unlocked."""
        self._require_unlocked()
        self._kdf = kdf_params or KdfParams.generate()
        self._key = crypto.derive_key(new_passphrase, self._kdf)
        self.save()

    def save(self) -> None:
        """Re-seal the payload with a fresh nonce and atomically write it."""
        self._require_unlocked()
        assert self._kdf is not None and self._payload is not None
        header = {
            "format": FORMAT,
            "version": ENVELOPE_VERSION,
            "kdf": self._kdf.to_dict(),
            "cipher": CIPHER,
        }
        plaintext = json.dumps(self._payload.to_dict(), separators=(",", ":")).encode("utf-8")
        blob = crypto.seal(self._key, plaintext, aad=_aad(header))
        envelope = {**header, "blob": crypto.b64(blob)}
        self._atomic_write(json.dumps(envelope, separators=(",", ":")).encode("utf-8"))

    # ---- delegating data operations (require unlocked) -----------------
    @property
    def payload(self) -> VaultPayload:
        self._require_unlocked()
        assert self._payload is not None
        return self._payload

    def collections(self):
        return list(self.payload.collections.values())

    def add_collection(self, label: str, *, aliases: list[str] | None = None):
        return self.payload.add_collection(label, aliases=aliases)

    def remove_collection(self, collection_id: str) -> None:
        self.payload.remove_collection(collection_id)

    def resolve_collection(self, ref: str):
        return self.payload.resolve_collection(ref)

    def add_item(
        self,
        collection_ref: str,
        label: str,
        attributes: dict[str, str],
        secret: bytes,
        *,
        content_type: str = "text/plain",
    ) -> Item:
        col = self.payload.resolve_collection(collection_ref)
        if col is None:
            raise UnknownCollection(collection_ref)
        return self.payload.add_item(
            col.id, label, attributes, secret, content_type=content_type
        )

    def get_item(self, collection_ref: str, item_id: str) -> Item | None:
        col = self.payload.resolve_collection(collection_ref)
        return self.payload.get_item(col.id, item_id) if col else None

    def remove_item(self, collection_ref: str, item_id: str) -> None:
        col = self.payload.resolve_collection(collection_ref)
        if col:
            self.payload.remove_item(col.id, item_id)

    def search(self, attributes: dict[str, str]) -> list[tuple[str, Item]]:
        return self.payload.search(attributes)

    def find_item(self, item_id: str) -> tuple[str, Item] | None:
        return self.payload.find_item(item_id)

    # ---- internals -----------------------------------------------------
    def _require_unlocked(self) -> None:
        if self.is_locked:
            raise VaultLocked("vault is locked")

    def _read_envelope(self) -> tuple[dict, bytes]:
        try:
            raw = self.path.read_bytes()
            envelope = json.loads(raw)
        except (OSError, ValueError) as exc:
            raise VaultCorrupt(f"cannot read vault envelope: {exc}") from exc
        if not isinstance(envelope, dict) or "blob" not in envelope or "kdf" not in envelope:
            raise VaultCorrupt("vault envelope missing required fields")
        blob = crypto.unb64(envelope["blob"])
        header = {k: v for k, v in envelope.items() if k != "blob"}
        return header, blob

    def _atomic_write(self, data: bytes) -> None:
        """Write to a sibling temp file (0600) then ``os.replace`` — never leave
        a half-written vault. The parent dir is created 0700."""
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def _aad(header: dict) -> bytes:
    """Canonical bytes of the envelope header (sorted keys) used as AEAD
    additional-authenticated-data, binding KDF params + version to the blob."""
    return json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")


__all__ = ["DEFAULT_VAULT_PATH", "BadPassphrase", "KdfParams", "Vault"]
