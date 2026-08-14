"""Pure keychain data-model tests — no cryptography, no I/O, CI-safe."""

from __future__ import annotations

import gest.core.keychain.model as model
from gest.core.keychain.model import Item, VaultPayload


def test_item_matches_subset_semantics():
    it = Item(id="1", label="x", attributes={"service": "rdp", "user": "bob", "host": "pc"})
    # a subset of attributes matches
    assert it.matches({"service": "rdp"})
    assert it.matches({"service": "rdp", "user": "bob"})
    # empty query matches everything
    assert it.matches({})
    # a wrong value or an absent key does not
    assert not it.matches({"service": "ssh"})
    assert not it.matches({"service": "rdp", "user": "alice"})
    assert not it.matches({"missing": "x"})


def test_item_round_trips_arbitrary_secret_bytes():
    raw = bytes(range(256))  # includes NULs and high bytes
    it = Item(id="1", label="k", attributes={"a": "b"}, secret=raw, content_type="app/x")
    back = Item.from_dict(it.to_dict())
    assert back.secret == raw
    assert back.attributes == {"a": "b"}
    assert back.content_type == "app/x"


def test_payload_round_trip_preserves_structure():
    p = VaultPayload()
    col = p.add_collection("login", aliases=["default"])
    p.add_item(col.id, "wifi", {"ssid": "home"}, b"pw1")
    p.add_item(col.id, "rdp", {"host": "pc"}, b"pw2")

    back = VaultPayload.from_dict(p.to_dict())
    assert list(back.collections) == list(p.collections)
    rcol = next(iter(back.collections.values()))
    assert rcol.label == "login"
    assert rcol.aliases == ["default"]
    assert {i.label for i in rcol.items.values()} == {"wifi", "rdp"}


def test_from_dict_rejects_foreign_format():
    try:
        VaultPayload.from_dict({"format": "not-gest", "collections": {}})
    except ValueError:
        return
    raise AssertionError("expected ValueError for a foreign format tag")


def test_new_default_seeds_login_collection_aliased_default():
    p = VaultPayload.new_default()
    assert len(p.collections) == 1
    col = p.collection_by_alias("default")
    assert col is not None
    assert col.label == "login"


def test_resolve_collection_by_id_or_alias():
    p = VaultPayload()
    col = p.add_collection("login", aliases=["default"])
    assert p.resolve_collection(col.id) is col
    assert p.resolve_collection("default") is col
    assert p.resolve_collection("nope") is None


def test_item_crud_and_modified_bumps(monkeypatch):
    ticks = iter([100, 200, 300, 400, 500])
    monkeypatch.setattr(model, "_now", lambda: next(ticks))
    p = VaultPayload()
    col = p.add_collection("c")  # _now -> 100
    item = p.add_item(col.id, "k", {"a": "1"}, b"s")  # _now -> 200
    assert item.created == 200
    assert col.modified == 200

    updated = p.set_secret(col.id, item.id, b"s2")  # _now -> 300
    assert updated.secret == b"s2"
    assert updated.modified == 300

    p.remove_item(col.id, item.id)  # _now -> 400
    assert p.get_item(col.id, item.id) is None
    assert col.modified == 400


def test_search_spans_collections():
    p = VaultPayload()
    a = p.add_collection("a")
    b = p.add_collection("b")
    p.add_item(a.id, "one", {"kind": "rdp", "host": "h1"}, b"x")
    p.add_item(b.id, "two", {"kind": "rdp", "host": "h2"}, b"y")
    p.add_item(b.id, "three", {"kind": "ssh"}, b"z")

    rdp = p.search({"kind": "rdp"})
    assert len(rdp) == 2
    assert {it.label for _, it in rdp} == {"one", "two"}

    one = p.search({"kind": "rdp", "host": "h1"})
    assert len(one) == 1 and one[0][1].label == "one"

    # empty query returns every item across collections
    assert len(p.search({})) == 3


def test_remove_collection_is_idempotent():
    p = VaultPayload()
    col = p.add_collection("c")
    p.remove_collection(col.id)
    p.remove_collection(col.id)  # no raise
    assert p.get_collection(col.id) is None


def test_ids_are_unique_across_many_items():
    p = VaultPayload()
    col = p.add_collection("c")
    ids = {p.add_item(col.id, f"k{i}", {}, b"s").id for i in range(200)}
    assert len(ids) == 200


def test_copy_is_independent():
    p = VaultPayload()
    col = p.add_collection("c")
    p.add_item(col.id, "k", {"a": "1"}, b"s")
    clone = p.copy()
    # mutating the clone must not touch the original
    clone_col = next(iter(clone.collections.values()))
    clone.add_item(clone_col.id, "k2", {}, b"s2")
    assert len(next(iter(p.collections.values())).items) == 1
