"""Pure argv builders for the Wi-Fi tools. No I/O; CI-testable.

The passphrase is *not* an argv here: the backend feeds it to ``wpa_passphrase``
on stdin so it never appears in the process list.
"""

from __future__ import annotations


def wpa_passphrase_argv(ssid: str, *, wpa_passphrase: str = "wpa_passphrase") -> list[str]:
    """Hash a passphrase for ``ssid`` (`wpa_passphrase <ssid>`; passphrase on stdin)."""
    return [wpa_passphrase, ssid]


def iw_dev_argv(*, iw: str = "iw") -> list[str]:
    """List wireless interfaces (`iw dev`)."""
    return [iw, "dev"]


def iw_scan_argv(iface: str, *, iw: str = "iw") -> list[str]:
    """Scan for nearby networks on ``iface`` (`iw dev <iface> scan`)."""
    return [iw, "dev", iface, "scan"]


def wpa_cli_reconfigure_argv(*, wpa_cli: str = "wpa_cli") -> list[str]:
    """Ask a running wpa_supplicant to re-read its config (`wpa_cli reconfigure`)."""
    return [wpa_cli, "reconfigure"]
