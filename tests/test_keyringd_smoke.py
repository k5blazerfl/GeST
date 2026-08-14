"""Real-bus smoke test for helm-keyringd.

Brings the daemon up on an actual session bus and drives it with a real Secret
Service client (dbus_next, and ``secret-tool`` if present) — the end-to-end proof
the ``service.py`` D-Bus wiring works, which the dependency-light unit job cannot
give (it has neither ``dbus_next`` nor a bus).

Run it under a private session bus::

    dbus-run-session -- pytest tests/test_keyringd_smoke.py -q

It is excluded from the default CI subset and skips unless ``dbus_next``,
``cryptography`` and a session bus are all present.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

pytest.importorskip("dbus_next")
pytest.importorskip("cryptography")

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus

from gest.core.keychain.crypto import KdfParams
from gest.core.keychain.vault import Vault
from gest.keyringd import contract
from gest.keyringd.service import (
    ITEM_ATTRS_KEY,
    ITEM_LABEL_KEY,
    KeyringDaemon,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DBUS_SESSION_BUS_ADDRESS"),
    reason="no session bus; run under `dbus-run-session`",
)


def _unlocked_vault(path: str) -> Vault:
    cheap = KdfParams.generate(time_cost=1, memory_cost=8, parallelism=1)
    return Vault.create(path, "smoke-pw", kdf_params=cheap)


async def _proxy(client: MessageBus, path: str, iface: str):
    introspection = await client.introspect(contract.SECRETS_BUS_NAME, path)
    obj = client.get_proxy_object(contract.SECRETS_BUS_NAME, path, introspection)
    return obj.get_interface(iface)


async def test_secret_service_roundtrip(tmp_path):
    vault = _unlocked_vault(str(tmp_path / "smoke.vault"))
    daemon = KeyringDaemon(vault)
    await daemon.serve()  # live once this returns
    client = await MessageBus(bus_type=BusType.SESSION).connect()
    try:
        service = await _proxy(client, contract.SERVICE_PATH, contract.SERVICE_IFACE)

        # 1) open a plain session
        _output, session_path = await service.call_open_session("plain", Variant("s", ""))
        assert session_path.startswith(contract.SESSION_BASE)

        # 2) the seeded "login" collection is reachable via the `default` alias
        coll_path = await service.call_read_alias("default")
        assert coll_path != "/"
        collection = await _proxy(client, coll_path, contract.COLLECTION_IFACE)

        # 3) store an item
        props = {
            ITEM_LABEL_KEY: Variant("s", "smoke item"),
            ITEM_ATTRS_KEY: Variant("a{ss}", {"app": "smoke", "user": "bob"}),
        }
        secret = [session_path, b"", b"topsecret", "text/plain"]
        item_path, prompt = await collection.call_create_item(props, secret, False)
        assert item_path != "/" and prompt == contract.NO_PROMPT

        # 4) find it by attribute (service-wide search)
        unlocked, _locked = await service.call_search_items({"app": "smoke"})
        assert item_path in unlocked

        # 5) read the secret back over the session
        item = await _proxy(client, item_path, contract.ITEM_IFACE)
        got = await item.call_get_secret(session_path)
        assert bytes(got[2]) == b"topsecret"

        # 6) properties expose metadata but never the secret
        attrs = await item.get_attributes()
        assert attrs == {"app": "smoke", "user": "bob"}
        assert await item.get_label() == "smoke item"

        # and it actually landed in the on-disk vault
        assert len(vault.search({"app": "smoke"})) == 1
    finally:
        client.disconnect()
        daemon.disconnect()


async def test_secret_tool_interop(tmp_path):
    """If libsecret's `secret-tool` is installed, prove a real libsecret client
    can look up an item we stored — the true compatibility check."""
    if shutil.which("secret-tool") is None:
        pytest.skip("secret-tool (libsecret-tools) not installed")

    vault = _unlocked_vault(str(tmp_path / "smoke.vault"))
    daemon = KeyringDaemon(vault)
    await daemon.serve()
    client = await MessageBus(bus_type=BusType.SESSION).connect()
    try:
        service = await _proxy(client, contract.SERVICE_PATH, contract.SERVICE_IFACE)
        _output, session_path = await service.call_open_session("plain", Variant("s", ""))
        coll_path = await service.call_read_alias("default")
        collection = await _proxy(client, coll_path, contract.COLLECTION_IFACE)
        props = {
            ITEM_LABEL_KEY: Variant("s", "for secret-tool"),
            ITEM_ATTRS_KEY: Variant("a{ss}", {"service": "smoke-st"}),
        }
        await collection.call_create_item(props, [session_path, b"", b"via-dbus", "text/plain"],
                                          False)
    finally:
        client.disconnect()

    try:
        result = subprocess.run(
            ["secret-tool", "lookup", "service", "smoke-st"],
            capture_output=True, text=True, timeout=20,
        )
        assert result.returncode == 0, result.stderr
        assert "via-dbus" in result.stdout
    finally:
        daemon.disconnect()
