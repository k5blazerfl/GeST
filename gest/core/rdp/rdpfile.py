"""Read/write the Windows ``.rdp`` file format ↔ :class:`RdpProfile`.

``.rdp`` files are ``key:type:value`` lines (``s`` string, ``i`` int, ``b``
binary). Supporting the format means a ``.rdp`` handed to Gangway (via the Customs
MIME handler, or exported from Windows) round-trips, and a profile can be shared
back out. Pure and CI-testable.
"""

from __future__ import annotations

from gest.core.rdp.model import (
    QUALITY_BALANCED,
    QUALITY_LAN,
    QUALITY_WAN,
    RdpProfile,
)


def _int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _split_addr(addr: str) -> tuple[str, int]:
    host, sep, port = addr.rpartition(":")
    if sep and port.isdigit():
        return host, int(port)
    return addr, 3389


def _quality_to_conn_type(quality: str) -> int:
    return {QUALITY_LAN: 6, QUALITY_BALANCED: 2, QUALITY_WAN: 1}.get(quality, 2)


def _conn_type_to_quality(conn_type: int) -> str:
    if conn_type >= 5:
        return QUALITY_LAN
    if conn_type <= 1:
        return QUALITY_WAN
    return QUALITY_BALANCED


def render(profile: RdpProfile) -> str:
    addr = profile.host + (f":{profile.port}" if profile.port != 3389 else "")
    lines = [
        f"full address:s:{addr}",
        f"screen mode id:i:{2 if profile.fullscreen else 1}",
        f"desktopwidth:i:{profile.width}",
        f"desktopheight:i:{profile.height}",
        f"use multimon:i:{1 if profile.multimon else 0}",
        f"dynamic resolution:i:{1 if profile.dynamic_resolution else 0}",
        f"redirectclipboard:i:{1 if profile.clipboard else 0}",
        f"audiomode:i:{0 if profile.audio_output else 2}",
        f"audiocapturemode:i:{1 if profile.microphone else 0}",
        f"redirectprinters:i:{1 if profile.printers else 0}",
        f"drivestoredirect:s:{'*' if profile.drive_redirect else ''}",
        f"enablecredsspsupport:i:{1 if profile.nla else 0}",
        f"connection type:i:{_quality_to_conn_type(profile.quality)}",
    ]
    if profile.username:
        lines.insert(1, f"username:s:{profile.username}")
    if profile.domain:
        lines.append(f"domain:s:{profile.domain}")
    if profile.gateway_host:
        lines.append(f"gatewayhostname:s:{profile.gateway_host}")
        lines.append("gatewayusagemethod:i:1")
    return "\n".join(lines) + "\n"


def parse(text: str, name: str) -> RdpProfile:
    kv: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3:
            kv[parts[0].strip().lower()] = parts[2]
    host, port = _split_addr(kv.get("full address", ""))
    return RdpProfile(
        name=name,
        host=host,
        port=port,
        username=kv.get("username", ""),
        domain=kv.get("domain", ""),
        fullscreen=kv.get("screen mode id", "2") == "2",
        width=_int(kv.get("desktopwidth", ""), 1920),
        height=_int(kv.get("desktopheight", ""), 1080),
        multimon=kv.get("use multimon", "0") == "1",
        dynamic_resolution=kv.get("dynamic resolution", "0") == "1",
        gateway_host=kv.get("gatewayhostname", ""),
        quality=_conn_type_to_quality(_int(kv.get("connection type", ""), 2)),
        clipboard=kv.get("redirectclipboard", "1") == "1",
        audio_output=kv.get("audiomode", "0") == "0",
        microphone=kv.get("audiocapturemode", "0") == "1",
        printers=kv.get("redirectprinters", "0") == "1",
        drive_redirect=kv.get("drivestoredirect", "") == "*",
        nla=kv.get("enablecredsspsupport", "1") == "1",
    )
