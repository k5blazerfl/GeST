"""Parse/validate/render wpa_supplicant.conf network blocks — pure, CI-testable.

The file is a header (``ctrl_interface``, ``update_config``) followed by
``network={ … }`` blocks. This module reads those blocks, adds/removes them by
SSID, and renders open-network blocks; secured blocks come from ``wpa_passphrase``
(run in the backend) so the raw passphrase never passes through here.
"""

from __future__ import annotations

import re

from gest.core.wifi.model import WifiNetwork

WPA_CONF = "/etc/wpa_supplicant/wpa_supplicant.conf"
HEADER = "ctrl_interface=/run/wpa_supplicant\nupdate_config=1\n"

_SSID_RE = re.compile(r'ssid="((?:[^"\\]|\\.)*)"')
_KEYMGMT_RE = re.compile(r"key_mgmt=(\S+)")


def valid_ssid(ssid: str) -> bool:
    if not 1 <= len(ssid.encode("utf-8")) <= 32:
        return False
    # Keep it renderable inside a quoted ssid="…" without escaping games.
    return all(ord(c) >= 32 for c in ssid) and not any(c in ssid for c in '"\\\n\r')


def valid_passphrase(passphrase: str) -> bool:
    # WPA-PSK ASCII passphrase length is 8..63 printable characters.
    return 8 <= len(passphrase) <= 63 and all(32 <= ord(c) <= 126 for c in passphrase)


# --- block reading ----------------------------------------------------------

def _segments(text: str):
    """Yield ('line', str) for non-block lines and ('block', ssid, text) for
    each ``network={ … }`` block, preserving order."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("network=") and "{" in line:
            block = [line]
            i += 1
            while i < len(lines):
                block.append(lines[i])
                closed = lines[i].strip() == "}"
                i += 1
                if closed:
                    break
            btext = "\n".join(block)
            yield ("block", block_ssid(btext), btext)
        else:
            yield ("line", line)
            i += 1


def block_ssid(block: str) -> str | None:
    match = _SSID_RE.search(block)
    return match.group(1) if match else None


def parse_networks(text: str) -> list[WifiNetwork]:
    """Every configured network (ssid + key_mgmt) in ``text``."""
    networks: list[WifiNetwork] = []
    for seg in _segments(text):
        if seg[0] == "block" and seg[1]:
            km = _KEYMGMT_RE.search(seg[2])
            networks.append(WifiNetwork(seg[1], km.group(1) if km else "WPA-PSK"))
    return networks


# --- block editing ----------------------------------------------------------

def ensure_header(text: str) -> str:
    """Prepend the ctrl_interface/update_config header if it isn't present."""
    if "ctrl_interface=" in text:
        return text
    if text and not text.startswith("\n"):
        return HEADER + "\n" + text
    return HEADER + text


def remove_network(text: str, ssid: str) -> str:
    """Return ``text`` with every ``network`` block for ``ssid`` removed."""
    out: list[str] = []
    for seg in _segments(text):
        if seg[0] == "block" and seg[1] == ssid:
            continue
        out.append(seg[2] if seg[0] == "block" else seg[1])
    body = "\n".join(out).rstrip("\n")
    return body + "\n" if body else ""


def append_network(text: str, block: str) -> str:
    """Append a network ``block`` (ensuring the header and a clean separator)."""
    base = ensure_header(text)
    if base and not base.endswith("\n"):
        base += "\n"
    block = block.strip("\n") + "\n"
    return base + "\n" + block if base.strip() else base + block


def render_open_network(ssid: str) -> str:
    """A ``network`` block for an open (no-password) network."""
    return f'network={{\n\tssid="{ssid}"\n\tkey_mgmt=NONE\n}}\n'


def sanitize_block(wpa_passphrase_output: str) -> str:
    """Extract the network block from ``wpa_passphrase`` output, dropping the
    plaintext ``#psk="…"`` comment it emits so the passphrase is never stored."""
    kept: list[str] = []
    inside = False
    for line in wpa_passphrase_output.splitlines():
        stripped = line.strip()
        if stripped.startswith("network=") and "{" in stripped:
            inside = True
        if inside:
            if stripped.startswith("#psk"):
                continue
            kept.append(line)
        if stripped == "}":
            break
    return "\n".join(kept) + "\n" if kept else ""
