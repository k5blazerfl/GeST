"""``helm-keyringd`` — the dbus_next Secret Service objects and the daemon.

This is the only keyringd module that imports ``dbus_next``; every non-trivial
decision lives in :mod:`gest.keyringd.store`/``paths``/``session`` (all pure and
CI-tested). Like ``gest.coreservice``, the bus wiring here is validated on a real
session bus, not in the dependency-light CI job.

Scope: the Secret Service **store/lookup path** over a vault unlocked at startup —
``OpenSession(plain)``, ``SearchItems``, ``GetSecrets``, ``CreateCollection``,
``CreateItem``, ``GetSecret``/``SetSecret``, ``Delete``, and the read properties
clients need. Prompts, the DH transport, TPM sealing and PAM auto-unlock are later
phases; here every operation runs unlocked and returns ``NO_PROMPT``.
"""

from __future__ import annotations

import asyncio
import os
import sys

from dbus_next import BusType, DBusError, Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method, signal

from gest.keyringd import contract, paths, store
from gest.keyringd.session import SessionRegistry

# a{sv} property keys defined by the spec.
COLLECTION_LABEL_KEY = "org.freedesktop.Secret.Collection.Label"
ITEM_LABEL_KEY = "org.freedesktop.Secret.Item.Label"
ITEM_ATTRS_KEY = "org.freedesktop.Secret.Item.Attributes"

# Spec error names.
ERR_NO_SESSION = "org.freedesktop.Secret.Error.NoSession"
ERR_NO_OBJECT = "org.freedesktop.Secret.Error.NoSuchObject"
ERR_NOT_SUPPORTED = "org.freedesktop.DBus.Error.NotSupported"


def _prop_str(props: dict, key: str, default: str = "") -> str:
    variant = props.get(key)
    return variant.value if variant is not None else default


def _prop_attrs(props: dict, key: str) -> dict[str, str]:
    variant = props.get(key)
    return {str(k): str(v) for k, v in dict(variant.value).items()} if variant is not None else {}


class SessionInterface(ServiceInterface):
    def __init__(self, daemon: KeyringDaemon, path: str) -> None:
        super().__init__(contract.SESSION_IFACE)
        self._daemon = daemon
        self._path = path

    @method()
    def Close(self):
        self._daemon.close_session(self._path)


class ItemInterface(ServiceInterface):
    def __init__(self, daemon: KeyringDaemon, cid: str, iid: str) -> None:
        super().__init__(contract.ITEM_IFACE)
        self._daemon = daemon
        self._cid = cid
        self._iid = iid

    @method()
    def GetSecret(self, session: "o") -> "(oayays)":
        sess = self._daemon.sessions.get(session)
        if sess is None:
            raise DBusError(ERR_NO_SESSION, "unknown session")
        secret = store.item_secret(self._daemon.vault, self._cid, self._iid)
        if secret is None:
            raise DBusError(ERR_NO_OBJECT, "no such item")
        params, value = sess.encode(secret)
        return [session, params, value, "text/plain"]

    @method()
    def SetSecret(self, secret: "(oayays)"):
        session_path, params, value, _ct = secret
        sess = self._daemon.sessions.get(session_path)
        if sess is None:
            raise DBusError(ERR_NO_SESSION, "unknown session")
        plaintext = sess.decode(bytes(params), bytes(value))
        if not store.set_item_secret(self._daemon.vault, self._cid, self._iid, plaintext):
            raise DBusError(ERR_NO_OBJECT, "no such item")

    @method()
    def Delete(self) -> "o":
        self._daemon.remove_item(self._cid, self._iid)
        return contract.NO_PROMPT

    @dbus_property(access=PropertyAccess.READ)
    def Locked(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Attributes(self) -> "a{ss}":
        return store.item_attributes(self._daemon.vault, self._cid, self._iid) or {}

    @dbus_property()
    def Label(self) -> "s":
        return store.item_label(self._daemon.vault, self._cid, self._iid) or ""

    @Label.setter
    def Label(self, value: "s"):
        self._daemon.vault.update_item(self._cid, self._iid, label=value)
        self._daemon.vault.save()

    @dbus_property(access=PropertyAccess.READ)
    def Created(self) -> "t":
        times = store.item_times(self._daemon.vault, self._cid, self._iid)
        return times[0] if times else 0

    @dbus_property(access=PropertyAccess.READ)
    def Modified(self) -> "t":
        times = store.item_times(self._daemon.vault, self._cid, self._iid)
        return times[1] if times else 0


class CollectionInterface(ServiceInterface):
    def __init__(self, daemon: KeyringDaemon, cid: str) -> None:
        super().__init__(contract.COLLECTION_IFACE)
        self._daemon = daemon
        self._cid = cid

    @method()
    def CreateItem(self, properties: "a{sv}", secret: "(oayays)",
                   replace: "b") -> "oo":
        label = _prop_str(properties, ITEM_LABEL_KEY)
        attrs = _prop_attrs(properties, ITEM_ATTRS_KEY)
        session_path, params, value, _ct = secret
        sess = self._daemon.sessions.get(session_path)
        if sess is None:
            raise DBusError(ERR_NO_SESSION, "unknown session")
        plaintext = sess.decode(bytes(params), bytes(value))
        iid = store.create_item(self._daemon.vault, self._cid, label, attrs, plaintext, replace)
        if iid is None:
            raise DBusError(ERR_NO_OBJECT, "no such collection")
        item_path = paths.item_path(self._cid, iid)
        if item_path not in self._daemon.items:
            self._daemon.export_item(self._cid, iid)
        self.ItemCreated(item_path)
        return [item_path, contract.NO_PROMPT]

    @method()
    def SearchItems(self, attributes: "a{ss}") -> "ao":
        return store.collection_search_item_paths(self._daemon.vault, self._cid, attributes)

    @method()
    def Delete(self) -> "o":
        self._daemon.remove_collection(self._cid)
        return contract.NO_PROMPT

    @dbus_property(access=PropertyAccess.READ)
    def Items(self) -> "ao":
        return store.collection_item_paths(self._daemon.vault, self._cid)

    @dbus_property(access=PropertyAccess.READ)
    def Label(self) -> "s":
        return store.collection_label(self._daemon.vault, self._cid) or ""

    @dbus_property(access=PropertyAccess.READ)
    def Locked(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Created(self) -> "t":
        times = store.collection_times(self._daemon.vault, self._cid)
        return times[0] if times else 0

    @dbus_property(access=PropertyAccess.READ)
    def Modified(self) -> "t":
        times = store.collection_times(self._daemon.vault, self._cid)
        return times[1] if times else 0

    @signal()
    def ItemCreated(self, item) -> "o":
        return item

    @signal()
    def ItemDeleted(self, item) -> "o":
        return item


class ServiceInterfaceImpl(ServiceInterface):
    def __init__(self, daemon: KeyringDaemon) -> None:
        super().__init__(contract.SERVICE_IFACE)
        self._daemon = daemon

    @method()
    def OpenSession(self, algorithm: "s", input: "v") -> "vo":
        if algorithm == contract.ALGO_PLAIN:
            path, _sess = self._daemon.sessions.open_plain(paths.session_path)
            self._daemon.export_session(path)
            return [Variant("s", ""), path]
        if algorithm == contract.ALGO_DH:
            client_public = bytes(input.value)
            path, server_public, _sess = self._daemon.sessions.open_dh(
                client_public, paths.session_path)
            self._daemon.export_session(path)
            return [Variant("ay", server_public), path]
        raise DBusError(ERR_NOT_SUPPORTED, f"algorithm {algorithm!r} not supported")

    @method()
    def SearchItems(self, attributes: "a{ss}") -> "aoao":
        return [store.search_item_paths(self._daemon.vault, attributes), []]

    @method()
    def Unlock(self, objects: "ao") -> "aoo":
        return [objects, contract.NO_PROMPT]  # vault already unlocked

    @method()
    def Lock(self, objects: "ao") -> "aoo":
        return [[], contract.NO_PROMPT]  # per-object locking is a later phase

    @method()
    def GetSecrets(self, items: "ao", session: "o") -> "a{o(oayays)}":
        sess = self._daemon.sessions.get(session)
        if sess is None:
            raise DBusError(ERR_NO_SESSION, "unknown session")
        out: dict[str, list] = {}
        for path in items:
            parsed = paths.parse_item_path(path)
            if parsed is None:
                continue
            secret = store.item_secret(self._daemon.vault, parsed[0], parsed[1])
            if secret is not None:
                params, value = sess.encode(secret)
                out[path] = [session, params, value, "text/plain"]
        return out

    @method()
    def CreateCollection(self, properties: "a{sv}", alias: "s") -> "oo":
        label = _prop_str(properties, COLLECTION_LABEL_KEY)
        cid = store.create_collection(self._daemon.vault, label, alias)
        self._daemon.export_collection(cid)
        path = paths.collection_path(cid)
        self.CollectionCreated(path)
        return [path, contract.NO_PROMPT]

    @method()
    def ReadAlias(self, name: "s") -> "o":
        cid = store.resolve_alias(self._daemon.vault, name)
        return paths.collection_path(cid) if cid else "/"

    @method()
    def SetAlias(self, name: "s", collection: "o"):
        parsed = paths.parse_collection_path(collection)
        if parsed is not None:
            store.set_alias(self._daemon.vault, name, parsed)

    @dbus_property(access=PropertyAccess.READ)
    def Collections(self) -> "ao":
        return store.collection_paths(self._daemon.vault)

    @signal()
    def CollectionCreated(self, collection) -> "o":
        return collection

    @signal()
    def CollectionDeleted(self, collection) -> "o":
        return collection


class KeyringDaemon:
    """Owns the bus connection, the unlocked vault, the session registry, and the
    set of exported Collection/Item/Session objects."""

    def __init__(self, vault) -> None:
        self.vault = vault
        self.sessions = SessionRegistry()
        self.bus: MessageBus | None = None
        self._service: ServiceInterfaceImpl | None = None
        self.collections: dict[str, CollectionInterface] = {}
        self.items: dict[str, ItemInterface] = {}
        self._session_ifaces: dict[str, SessionInterface] = {}

    async def serve(self) -> None:
        """Connect, export every object, and claim the well-known name — then
        return. The daemon is live once this resolves; :meth:`start` blocks after
        it, while the smoke test drives a client and then disconnects."""
        self.bus = await MessageBus(bus_type=BusType.SESSION).connect()
        self._service = ServiceInterfaceImpl(self)
        self.bus.export(contract.SERVICE_PATH, self._service)
        for col in self.vault.collections():
            self.export_collection(col.id)
            for iid in list(col.items):
                self.export_item(col.id, iid)
        await self.bus.request_name(contract.SECRETS_BUS_NAME)

    async def start(self) -> None:
        await self.serve()
        await self.bus.wait_for_disconnect()

    def disconnect(self) -> None:
        if self.bus is not None:
            self.bus.disconnect()

    # ---- object export management --------------------------------------
    def export_collection(self, cid: str) -> None:
        iface = CollectionInterface(self, cid)
        self.bus.export(paths.collection_path(cid), iface)
        self.collections[cid] = iface

    def export_item(self, cid: str, iid: str) -> None:
        path = paths.item_path(cid, iid)
        iface = ItemInterface(self, cid, iid)
        self.bus.export(path, iface)
        self.items[path] = iface

    def export_session(self, path: str) -> None:
        iface = SessionInterface(self, path)
        self.bus.export(path, iface)
        self._session_ifaces[path] = iface

    def close_session(self, path: str) -> None:
        self.sessions.close(path)
        iface = self._session_ifaces.pop(path, None)
        if iface is not None:
            self.bus.unexport(path, iface)

    def remove_item(self, cid: str, iid: str) -> None:
        store.delete_item(self.vault, cid, iid)
        path = paths.item_path(cid, iid)
        iface = self.items.pop(path, None)
        if iface is not None:
            self.bus.unexport(path, iface)
        col = self.collections.get(cid)
        if col is not None:
            col.ItemDeleted(path)

    def remove_collection(self, cid: str) -> None:
        col = self.vault.resolve_collection(cid)
        if col is not None:
            for iid in list(col.items):
                self.remove_item(cid, iid)
        self.vault.remove_collection(cid)
        self.vault.save()
        iface = self.collections.pop(cid, None)
        if iface is not None:
            self.bus.unexport(paths.collection_path(cid), iface)
        if self._service is not None:
            self._service.CollectionDeleted(paths.collection_path(cid))


def main() -> None:
    import getpass

    from gest.core.keychain.errors import KeychainError
    from gest.core.keychain.vault import DEFAULT_VAULT_PATH, Vault

    vault_path = os.environ.get("GEST_KEYRING_VAULT", DEFAULT_VAULT_PATH)
    vault = Vault(vault_path)
    if not vault.exists():
        sys.stderr.write(
            f"helm-keyringd: no vault at {vault.path}; run `keychainctl init` first.\n"
        )
        raise SystemExit(1)
    passphrase = os.environ.get("GEST_KEYRING_PASSPHRASE") or getpass.getpass("Vault passphrase: ")
    try:
        vault.unlock(passphrase)
    except KeychainError as exc:
        sys.stderr.write(f"helm-keyringd: cannot unlock vault ({exc}).\n")
        raise SystemExit(1) from exc

    daemon = KeyringDaemon(vault)
    try:
        asyncio.run(daemon.start())
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # bus not running, name taken, etc.
        sys.stderr.write(f"helm-keyringd: could not start ({exc}). Is the session bus running?\n")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
