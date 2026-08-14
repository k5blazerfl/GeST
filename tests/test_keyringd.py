"""CI-safe tests for helm-keyringd's pure layers: contract, path codec, session
registry, and the store adapter.

The store is exercised against a *real* unlocked Vault whose payload is set
directly and whose ``save`` is stubbed — so we test the genuine ref-resolving
delegation without ``cryptography`` or a disk, and without importing the
``dbus_next`` service module.
"""

from __future__ import annotations

import importlib.util

import pytest

from gest.core.keychain.model import VaultPayload
from gest.core.keychain.vault import Vault
from gest.keyringd import contract, dh, paths, store
from gest.keyringd.session import DhSession, SessionRegistry

_HAS_CRYPTO = importlib.util.find_spec("cryptography") is not None
requires_crypto = pytest.mark.skipif(not _HAS_CRYPTO, reason="cryptography not installed")


class _FakeVault(Vault):
    """A real Vault (so store hits the genuine ref-resolving logic) but with
    sealing/disk stubbed out — no cryptography or filesystem in these tests."""

    def save(self) -> None:  # type: ignore[override]
        pass


def fake_vault() -> Vault:
    v = _FakeVault("/nonexistent/keyringd-test.vault")
    v._payload = VaultPayload.new_default()  # seeds the "login"/"default" collection
    v._key = b"\x00" * 32  # marks it unlocked; no crypto is exercised
    return v


# ---- contract ----------------------------------------------------------
def test_contract_uses_standard_freedesktop_names():
    assert contract.SECRETS_BUS_NAME == "org.freedesktop.secrets"
    assert contract.SERVICE_PATH == "/org/freedesktop/secrets"
    assert contract.SERVICE_IFACE == "org.freedesktop.Secret.Service"
    assert contract.ITEM_IFACE == "org.freedesktop.Secret.Item"
    assert contract.NO_PROMPT == "/"


# ---- path codec --------------------------------------------------------
def test_path_round_trips():
    assert paths.parse_collection_path(paths.collection_path("abc123")) == "abc123"
    assert paths.parse_item_path(paths.item_path("c1", "i1")) == ("c1", "i1")


def test_collection_path_is_not_an_item_path():
    # a bare collection path must not decode as an item path, and vice versa
    assert paths.parse_item_path(paths.collection_path("c1")) is None
    assert paths.parse_collection_path(paths.item_path("c1", "i1")) is None


def test_parse_rejects_foreign_or_malformed_paths():
    for bad in ("/org/freedesktop/secrets/session/x", "/other/c1", "not a path",
                "/org/freedesktop/secrets/collection/a/b/c"):
        assert paths.parse_item_path(bad) is None or bad.count("/") != 6
    assert paths.parse_collection_path("/org/freedesktop/secrets/collection/") is None


def test_unsafe_ids_are_rejected_on_build():
    for bad in ("a/b", "a b", "a.b", "../etc"):
        try:
            paths.collection_path(bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


# ---- session registry --------------------------------------------------
def test_plain_session_open_get_close_and_identity_transport():
    reg = SessionRegistry()
    path, sess = reg.open_plain(paths.session_path)
    assert reg.get(path) is sess
    params, value = sess.encode(b"\x00secret\xff")
    assert params == b"" and value == b"\x00secret\xff"  # plain = identity, no IV
    assert sess.decode(b"", b"abc") == b"abc"
    assert reg.close(path) is True
    assert reg.get(path) is None
    assert reg.close(path) is False  # idempotent


def test_dh_key_agreement_matches_between_peers():
    # A client generates a keypair; the registry does the server side. Both must
    # independently derive the *same* AES key — pure stdlib (pow + HKDF), so this
    # catches a broken DH group / HKDF without cryptography or a bus.
    client_private, client_public = dh.generate_keypair()
    reg = SessionRegistry()
    path, server_public, session = reg.open_dh(client_public, paths.session_path)
    client_key = dh.derive_aes_key(dh.shared_secret(client_private, server_public))
    assert client_key == session.aes_key
    assert len(session.aes_key) == 16  # AES-128
    assert len(server_public) == dh.KEY_BYTES == 128
    assert reg.get(path) is session


def test_dh_public_keys_are_fixed_width():
    _priv, pub = dh.generate_keypair()
    assert len(pub) == 128  # left-zero-padded even when the value is short


@requires_crypto
def test_dh_transport_encrypts_and_round_trips():
    key = dh.derive_aes_key(b"\x11" * dh.KEY_BYTES)
    session = DhSession(id="s1", aes_key=key)
    plaintext = b"a rather secret value \x00\xff"
    params, value = session.encode(plaintext)
    assert len(params) == 16  # the IV
    assert value != plaintext  # actually encrypted
    assert session.decode(params, value) == plaintext
    # a second encryption uses a fresh IV, so ciphertext differs
    params2, value2 = session.encode(plaintext)
    assert params2 != params and value2 != value


# ---- store adapter -----------------------------------------------------
def _default_cid(vault: Vault) -> str:
    return vault.resolve_collection("default").id


def test_create_search_and_get_item():
    v = fake_vault()
    cid = _default_cid(v)
    iid = store.create_item(v, cid, "rdp", {"host": "pc"}, b"s3cr3t", replace=False)
    assert iid is not None

    item_paths = store.search_item_paths(v, {"host": "pc"})
    assert item_paths == [paths.item_path(cid, iid)]
    assert store.item_secret(v, cid, iid) == b"s3cr3t"
    assert store.item_attributes(v, cid, iid) == {"host": "pc"}
    assert store.item_label(v, cid, iid) == "rdp"


def test_create_item_replace_overwrites_same_attributes():
    v = fake_vault()
    cid = _default_cid(v)
    first = store.create_item(v, cid, "a", {"k": "1"}, b"old", replace=False)
    again = store.create_item(v, cid, "a2", {"k": "1"}, b"new", replace=True)
    assert again == first  # same item id reused
    assert store.item_secret(v, cid, first) == b"new"
    assert store.item_label(v, cid, first) == "a2"
    # without replace, a second identical-attr item is a distinct item
    third = store.create_item(v, cid, "a3", {"k": "1"}, b"other", replace=False)
    assert third != first


def test_set_item_secret_and_delete():
    v = fake_vault()
    cid = _default_cid(v)
    iid = store.create_item(v, cid, "x", {"a": "b"}, b"one", replace=False)
    assert store.set_item_secret(v, cid, iid, b"two") is True
    assert store.item_secret(v, cid, iid) == b"two"
    assert store.delete_item(v, cid, iid) is True
    assert store.item_secret(v, cid, iid) is None
    assert store.delete_item(v, cid, iid) is False  # already gone


def test_collection_scoped_search():
    v = fake_vault()
    cid = _default_cid(v)
    other = store.create_collection(v, "other")
    store.create_item(v, cid, "in-default", {"k": "v"}, b"1", replace=False)
    store.create_item(v, other, "in-other", {"k": "v"}, b"2", replace=False)
    # service-wide search sees both; collection-scoped sees one
    assert len(store.search_item_paths(v, {"k": "v"})) == 2
    scoped = store.collection_search_item_paths(v, cid, {"k": "v"})
    assert len(scoped) == 1 and scoped[0].startswith(paths.collection_path(cid))


def test_create_item_unknown_collection_returns_none():
    v = fake_vault()
    assert store.create_item(v, "no-such", "l", {}, b"s", replace=False) is None


def test_collections_and_aliases():
    v = fake_vault()
    default_cid = _default_cid(v)
    assert paths.collection_path(default_cid) in store.collection_paths(v)
    assert store.resolve_alias(v, "default") == default_cid

    new_cid = store.create_collection(v, "work", alias="work")
    assert store.resolve_alias(v, "work") == new_cid
    assert store.set_alias(v, "extra", new_cid) is True
    assert store.resolve_alias(v, "extra") == new_cid
    assert store.set_alias(v, "x", "no-such-collection") is False


def test_collection_metadata_accessors():
    v = fake_vault()
    cid = _default_cid(v)
    assert store.collection_label(v, cid) == "login"
    created, modified = store.collection_times(v, cid)
    assert isinstance(created, int) and isinstance(modified, int)
