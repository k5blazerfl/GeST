"""Vault crypto + persistence tests.

Gated on ``cryptography`` (GeST's optional ``keychain`` dependency): they run in
CI, where the dep is installed, and skip on a host without it. Argon2id costs are
dialled right down so the KDF is fast under test.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("cryptography")

from gest.core.keychain.crypto import KdfParams  # noqa: E402
from gest.core.keychain.errors import (  # noqa: E402
    BadPassphrase,
    UnknownCollection,
    VaultCorrupt,
    VaultExists,
    VaultLocked,
    VaultNotFound,
)
from gest.core.keychain.vault import Vault  # noqa: E402

# Cheap KDF for tests: 1 pass, 8 KiB, 1 lane (Argon2id requires memory >= 8*lanes).
CHEAP = dict(time_cost=1, memory_cost=8, parallelism=1)


def _cheap_params():
    return KdfParams.generate(**CHEAP)


def test_create_then_reopen_round_trip(tmp_path):
    path = tmp_path / "v.vault"
    v = Vault.create(path, "hunter2", kdf_params=_cheap_params())
    col = v.resolve_collection("default")
    v.add_item(col.id, "rdp", {"host": "pc"}, b"s3cr3t")
    v.save()
    v.lock()

    v2 = Vault(path)
    assert v2.is_locked
    v2.unlock("hunter2")
    hits = v2.search({"host": "pc"})
    assert len(hits) == 1
    assert hits[0][1].secret == b"s3cr3t"


def test_wrong_passphrase_raises_badpassphrase(tmp_path):
    path = tmp_path / "v.vault"
    Vault.create(path, "correct horse", kdf_params=_cheap_params()).lock()
    v = Vault(path)
    with pytest.raises(BadPassphrase):
        v.unlock("wrong horse")


def test_tampered_ciphertext_is_rejected(tmp_path):
    path = tmp_path / "v.vault"
    Vault.create(path, "pw", kdf_params=_cheap_params()).lock()
    env = json.loads(path.read_bytes())
    # flip a character in the base64 blob
    blob = list(env["blob"])
    blob[10] = "A" if blob[10] != "A" else "B"
    env["blob"] = "".join(blob)
    path.write_bytes(json.dumps(env).encode())

    with pytest.raises(BadPassphrase):
        Vault(path).unlock("pw")


def test_tampered_kdf_header_breaks_aad(tmp_path):
    # The header is AEAD additional-data; changing time_cost must invalidate the
    # tag even though the blob is untouched.
    path = tmp_path / "v.vault"
    Vault.create(path, "pw", kdf_params=_cheap_params()).lock()
    env = json.loads(path.read_bytes())
    env["kdf"]["time_cost"] = env["kdf"]["time_cost"] + 5
    path.write_bytes(json.dumps(env).encode())

    with pytest.raises(BadPassphrase):
        Vault(path).unlock("pw")


def test_create_refuses_to_clobber(tmp_path):
    path = tmp_path / "v.vault"
    Vault.create(path, "pw", kdf_params=_cheap_params())
    with pytest.raises(VaultExists):
        Vault.create(path, "pw2", kdf_params=_cheap_params())


def test_unlock_missing_file_raises(tmp_path):
    with pytest.raises(VaultNotFound):
        Vault(tmp_path / "nope.vault").unlock("pw")


def test_operations_require_unlock(tmp_path):
    path = tmp_path / "v.vault"
    Vault.create(path, "pw", kdf_params=_cheap_params()).lock()
    v = Vault(path)  # locked
    with pytest.raises(VaultLocked):
        v.collections()
    with pytest.raises(VaultLocked):
        v.save()


def test_change_passphrase(tmp_path):
    path = tmp_path / "v.vault"
    v = Vault.create(path, "old", kdf_params=_cheap_params())
    col = v.resolve_collection("default")
    v.add_item(col.id, "k", {"a": "1"}, b"secret")
    v.save()
    v.change_passphrase("new", kdf_params=_cheap_params())
    v.lock()

    reopened = Vault(path)
    with pytest.raises(BadPassphrase):
        reopened.unlock("old")
    reopened.unlock("new")
    assert reopened.search({"a": "1"})[0][1].secret == b"secret"


def test_add_item_to_unknown_collection_raises(tmp_path):
    path = tmp_path / "v.vault"
    v = Vault.create(path, "pw", kdf_params=_cheap_params())
    with pytest.raises(UnknownCollection):
        v.add_item("no-such-collection", "k", {}, b"s")


def test_corrupt_envelope_raises(tmp_path):
    path = tmp_path / "v.vault"
    path.write_bytes(b"{ this is not json")
    with pytest.raises(VaultCorrupt):
        Vault(path).unlock("pw")


def test_atomic_write_leaves_no_tempfile(tmp_path):
    path = tmp_path / "sub" / "v.vault"
    Vault.create(path, "pw", kdf_params=_cheap_params()).save()
    leftovers = [p.name for p in path.parent.iterdir() if p.name != path.name]
    assert leftovers == []


def test_new_vault_seeds_default_collection(tmp_path):
    path = tmp_path / "v.vault"
    v = Vault.create(path, "pw", kdf_params=_cheap_params())
    assert v.resolve_collection("default") is not None
    assert v.resolve_collection("default").label == "login"
