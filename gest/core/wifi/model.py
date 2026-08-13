"""Data model for the Wi-Fi module."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class WifiNetwork:
    """One configured network, as read back from wpa_supplicant.conf.

    ``key_mgmt`` is ``"WPA-PSK"`` for a secured network or ``"NONE"`` for an open
    one. The PSK itself is never surfaced — only whether the network is secured.
    """

    ssid: str
    key_mgmt: str = "WPA-PSK"

    @property
    def secured(self) -> bool:
        return self.key_mgmt.upper() != "NONE"
