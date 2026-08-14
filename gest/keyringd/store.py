"""The pure adapter mapping Secret Service operations onto the vault.

Every function takes a ``vault`` (an unlocked :class:`gest.core.keychain.vault.
Vault`, or any object exposing the same small surface — the tests pass a
crypto-free fake) and returns plain data / object paths. No ``dbus_next`` here, so
the whole store/lookup logic is CI-testable without a bus or ``cryptography``.
"""

from __future__ import annotations

from collections.abc import Mapping

from gest.keyringd import paths


# ---- collections -------------------------------------------------------
def collection_paths(vault) -> list[str]:
    return [paths.collection_path(c.id) for c in vault.collections()]

def collection_item_paths(vault, cid: str) -> list[str]:
    col = vault.resolve_collection(cid)
    return [paths.item_path(cid, iid) for iid in col.items] if col else []

def collection_label(vault, cid: str) -> str | None:
    col = vault.resolve_collection(cid)
    return col.label if col else None

def collection_times(vault, cid: str) -> tuple[int, int] | None:
    col = vault.resolve_collection(cid)
    return (col.created, col.modified) if col else None

def create_collection(vault, label: str, alias: str = "") -> str:
    col = vault.add_collection(label, aliases=[alias] if alias else [])
    vault.save()
    return col.id

def resolve_alias(vault, alias: str) -> str | None:
    col = vault.resolve_collection(alias)
    return col.id if col else None

def set_alias(vault, name: str, cid: str) -> bool:
    """Add ``name`` as an alias of collection ``cid`` (idempotent)."""
    col = vault.resolve_collection(cid)
    if col is None:
        return False
    if name not in col.aliases:
        col.aliases.append(name)
        vault.save()
    return True


# ---- items -------------------------------------------------------------
def search_item_paths(vault, attributes: Mapping[str, str]) -> list[str]:
    """Item paths whose attributes match (freedesktop SearchItems semantics)."""
    return [paths.item_path(cid, item.id) for cid, item in vault.search(attributes)]

def collection_search_item_paths(vault, cid: str, attributes: Mapping[str, str]) -> list[str]:
    """SearchItems scoped to one collection."""
    col = vault.resolve_collection(cid)
    if not col:
        return []
    return [paths.item_path(cid, item.id) for item in col.items.values()
            if item.matches(attributes)]

def item_secret(vault, cid: str, iid: str) -> bytes | None:
    item = vault.get_item(cid, iid)
    return item.secret if item else None

def item_attributes(vault, cid: str, iid: str) -> dict[str, str] | None:
    item = vault.get_item(cid, iid)
    return dict(item.attributes) if item else None

def item_label(vault, cid: str, iid: str) -> str | None:
    item = vault.get_item(cid, iid)
    return item.label if item else None

def item_times(vault, cid: str, iid: str) -> tuple[int, int] | None:
    item = vault.get_item(cid, iid)
    return (item.created, item.modified) if item else None

def set_item_secret(vault, cid: str, iid: str, secret: bytes) -> bool:
    if vault.get_item(cid, iid) is None:
        return False
    vault.update_item(cid, iid, secret=secret)
    vault.save()
    return True

def delete_item(vault, cid: str, iid: str) -> bool:
    if vault.get_item(cid, iid) is None:
        return False
    vault.remove_item(cid, iid)
    vault.save()
    return True

def create_item(vault, cid: str, label: str, attributes: Mapping[str, str],
                secret: bytes, replace: bool) -> str | None:
    """Create an item, or (when ``replace``) overwrite an existing item whose
    attributes are identical. Returns the item id, or ``None`` if the collection
    is unknown."""
    col = vault.resolve_collection(cid)
    if col is None:
        return None
    wanted = dict(attributes)
    if replace:
        for iid, item in col.items.items():
            if item.attributes == wanted:
                vault.update_item(cid, iid, label=label, secret=secret)
                vault.save()
                return iid
    item = vault.add_item(cid, label, wanted, secret)
    vault.save()
    return item.id
