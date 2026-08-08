"""Read network interface state via `ip -j addr` (unprivileged)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

from gest.core.network.model import Interface
from gest.core.network.netifrc import InterfaceConfig, parse_conf_net

Runner = Callable[[list[str]], str]


def parse_ip_json(text: str) -> list[Interface]:
    """Parse the JSON from `ip -j addr` into Interface objects."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []
    interfaces: list[Interface] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        addrs = []
        for info in entry.get("addr_info", []):
            local = info.get("local")
            if local:
                prefix = info.get("prefixlen")
                addrs.append(f"{local}/{prefix}" if prefix is not None else local)
        interfaces.append(
            Interface(
                name=entry.get("ifname", "?"),
                state=entry.get("operstate", "UNKNOWN"),
                mac=entry.get("address", ""),
                addresses=addrs,
            )
        )
    return interfaces


def _default_runner(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True).stdout
    except OSError:
        return ""


def list_interfaces(runner: Runner | None = None) -> list[Interface]:
    run = runner or _default_runner
    return parse_ip_json(run(["ip", "-j", "addr"]))


def read_interface_config(iface: str, path: str = "/etc/conf.d/net") -> InterfaceConfig:
    """Current netifrc config for an interface (unprivileged read)."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = ""
    return parse_conf_net(text, iface)
