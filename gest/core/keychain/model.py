"""The vault's data model and plaintext format — pure, no cryptography.

Shaped to the freedesktop Secret Service object model so the daemon layer maps
onto it 1:1 later: a vault holds **collections**, each holding **items**, each
item being a ``(label, attributes, secret)`` triple. ``attributes`` are the
searchable, non-secret key/value pairs apps look items up by; ``secret`` is the
protected payload.

Everything here is deterministic given its inputs and free of I/O and crypto, so
the whole layer is CI-testable without a display, a bus, or ``cryptography``.
The only ambient inputs are the clock and the id source, both funnelled through
:func:`_now` / :func:`_gen_id` so tests can pin them.
"""

from __future__ import annotations

import base64
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass, field

FORMAT = "gest-keyring"
PAYLOAD_VERSION = 1

# The conventional default collection every keyring exposes; libsecret's
# ``SecretService`` stores into it when no collection is named.
DEFAULT_COLLECTION_LABEL = "login"
DEFAULT_ALIAS = "default"


def _now() -> int:
    """Whole-second unix timestamp (indirection so tests can pin it)."""
    return int(time.time())


def _gen_id() -> str:
    """A short, collision-resistant id (128 bits of os.urandom, hex)."""
    return secrets.token_hex(16)


@dataclass(slots=True)
class Item:
    """One stored secret and the non-secret attributes it is found by."""

    id: str
    label: str
    attributes: dict[str, str] = field(default_factory=dict)
    secret: bytes = b""
    content_type: str = "text/plain"
    created: int = 0
    modified: int = 0

    def matches(self, query: Mapping[str, str]) -> bool:
        """Secret Service ``SearchItems`` semantics: every queried attribute must
        be present and equal. An empty query matches every item."""
        return all(self.attributes.get(k) == v for k, v in query.items())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "attributes": dict(self.attributes),
            # base64 so arbitrary secret bytes survive JSON round-tripping
            "secret": base64.b64encode(self.secret).decode("ascii"),
            "content_type": self.content_type,
            "created": self.created,
            "modified": self.modified,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> Item:
        return cls(
            id=str(d["id"]),
            label=str(d.get("label", "")),
            attributes={str(k): str(v) for k, v in dict(d.get("attributes", {})).items()},
            secret=base64.b64decode(d.get("secret", "")),
            content_type=str(d.get("content_type", "text/plain")),
            created=int(d.get("created", 0)),
            modified=int(d.get("modified", 0)),
        )


@dataclass(slots=True)
class Collection:
    """A named group of items, optionally carrying aliases (e.g. ``default``)."""

    id: str
    label: str
    aliases: list[str] = field(default_factory=list)
    created: int = 0
    modified: int = 0
    items: dict[str, Item] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "aliases": list(self.aliases),
            "created": self.created,
            "modified": self.modified,
            "items": {iid: it.to_dict() for iid, it in self.items.items()},
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> Collection:
        return cls(
            id=str(d["id"]),
            label=str(d.get("label", "")),
            aliases=[str(a) for a in d.get("aliases", [])],
            created=int(d.get("created", 0)),
            modified=int(d.get("modified", 0)),
            items={
                str(iid): Item.from_dict(it) for iid, it in dict(d.get("items", {})).items()
            },
        )


@dataclass(slots=True)
class VaultPayload:
    """The decrypted contents of a vault: its collections, and the operations
    over them. This is what the crypto layer seals and unseals."""

    collections: dict[str, Collection] = field(default_factory=dict)

    # ---- serialization -------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "format": FORMAT,
            "version": PAYLOAD_VERSION,
            "collections": {cid: c.to_dict() for cid, c in self.collections.items()},
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> VaultPayload:
        if d.get("format") != FORMAT:
            raise ValueError(f"not a {FORMAT} payload")
        return cls(
            collections={
                str(cid): Collection.from_dict(c)
                for cid, c in dict(d.get("collections", {})).items()
            }
        )

    @classmethod
    def new_default(cls) -> VaultPayload:
        """A fresh payload seeded with the conventional ``login`` collection
        aliased ``default`` — what a brand-new vault starts with."""
        p = cls()
        p.add_collection(DEFAULT_COLLECTION_LABEL, aliases=[DEFAULT_ALIAS])
        return p

    # ---- collections ---------------------------------------------------
    def add_collection(self, label: str, *, aliases: list[str] | None = None) -> Collection:
        now = _now()
        col = Collection(id=_gen_id(), label=label, aliases=list(aliases or []),
                         created=now, modified=now)
        self.collections[col.id] = col
        return col

    def remove_collection(self, collection_id: str) -> None:
        self.collections.pop(collection_id, None)

    def get_collection(self, collection_id: str) -> Collection | None:
        return self.collections.get(collection_id)

    def collection_by_alias(self, alias: str) -> Collection | None:
        for col in self.collections.values():
            if alias in col.aliases:
                return col
        return None

    def resolve_collection(self, ref: str) -> Collection | None:
        """Look a collection up by id first, then by alias — the way callers
        naturally reference ``default``/``login`` or a concrete id."""
        return self.get_collection(ref) or self.collection_by_alias(ref)

    # ---- items ---------------------------------------------------------
    def add_item(self, collection_id: str, label: str, attributes: Mapping[str, str],
                 secret: bytes, *, content_type: str = "text/plain") -> Item:
        col = self.collections[collection_id]
        now = _now()
        item = Item(
            id=_gen_id(),
            label=label,
            attributes=dict(attributes),
            secret=bytes(secret),
            content_type=content_type,
            created=now,
            modified=now,
        )
        col.items[item.id] = item
        col.modified = now
        return item

    def get_item(self, collection_id: str, item_id: str) -> Item | None:
        col = self.collections.get(collection_id)
        return col.items.get(item_id) if col else None

    def remove_item(self, collection_id: str, item_id: str) -> None:
        col = self.collections.get(collection_id)
        if col and item_id in col.items:
            del col.items[item_id]
            col.modified = _now()

    def set_secret(self, collection_id: str, item_id: str, secret: bytes) -> Item:
        item = self.get_item(collection_id, item_id)
        if item is None:
            raise KeyError(item_id)
        item.secret = bytes(secret)
        item.modified = _now()
        return item

    def find_item(self, item_id: str) -> tuple[str, Item] | None:
        """Locate an item by its id across all collections, returning
        ``(collection_id, item)`` or ``None`` — the id is globally unique, so
        callers (e.g. the CLI) can address an item without naming its
        collection."""
        for cid, col in self.collections.items():
            if item_id in col.items:
                return cid, col.items[item_id]
        return None

    def search(self, attributes: Mapping[str, str]) -> list[tuple[str, Item]]:
        """All ``(collection_id, item)`` across every collection whose attributes
        match — freedesktop ``SearchItems`` semantics (query is a subset)."""
        hits: list[tuple[str, Item]] = []
        for cid, col in self.collections.items():
            for item in col.items.values():
                if item.matches(attributes):
                    hits.append((cid, item))
        return hits

    def copy(self) -> VaultPayload:
        """A deep-ish copy (dataclasses replaced, dicts rebuilt) — handy for
        callers that want to mutate a snapshot without touching the live one."""
        return VaultPayload.from_dict(self.to_dict())


__all__ = [
    "DEFAULT_ALIAS",
    "DEFAULT_COLLECTION_LABEL",
    "FORMAT",
    "PAYLOAD_VERSION",
    "Collection",
    "Item",
    "VaultPayload",
]
