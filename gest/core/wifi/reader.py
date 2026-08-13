"""Read configured Wi-Fi networks and parse tool output.

wpa_supplicant.conf is root-only (0600), so the unprivileged read returns "" on
an installed system — the list is populated when GeST runs as root (a live CD,
the install path) and otherwise stays empty. The scan/interface parsers are pure.
"""

from __future__ import annotations

from gest.core.wifi import config
from gest.core.wifi.model import WifiNetwork


def read_conf(path: str = config.WPA_CONF) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def configured_networks(path: str = config.WPA_CONF) -> list[WifiNetwork]:
    return config.parse_networks(read_conf(path))


def parse_iw_dev(text: str) -> list[str]:
    """Interface names from ``iw dev`` output (lines like ``Interface wlan0``)."""
    names: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Interface "):
            names.append(stripped.split(None, 1)[1].strip())
    return names


def parse_scan_ssids(text: str) -> list[str]:
    """Unique, non-empty SSIDs from ``iw dev <iface> scan`` output, in first-seen
    order (hidden networks emit an empty ``SSID:`` which is skipped)."""
    seen: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("SSID:"):
            ssid = stripped[len("SSID:"):].strip()
            if ssid and ssid not in seen:
                seen.append(ssid)
    return seen
