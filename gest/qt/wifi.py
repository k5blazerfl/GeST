"""Wi-Fi module logic: pure label + sync bridges to the Wifi backend."""

from __future__ import annotations

from gest.core.wifi.model import WifiNetwork
from gest.qt.backend import run_backend


def wifi_label(net: WifiNetwork) -> str:
    return f"{net.ssid} \U0001f512" if net.secured else net.ssid  # 🔒


def add_network(ssid: str, passphrase: str) -> tuple[bool, str]:
    async def run():
        from gest.core.wifi.backend_client import WifiBackend

        backend = await WifiBackend().connect()
        try:
            return await backend.add_network(ssid, passphrase)
        finally:
            await backend.close()

    return run_backend(run)


def remove_network(ssid: str) -> tuple[bool, str]:
    async def run():
        from gest.core.wifi.backend_client import WifiBackend

        backend = await WifiBackend().connect()
        try:
            return await backend.remove_network(ssid)
        finally:
            await backend.close()

    return run_backend(run)
