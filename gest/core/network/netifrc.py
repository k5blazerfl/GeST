"""Read/render netifrc interface config in /etc/conf.d/net.

Handles the common single-address case: an interface is either DHCP
(``config_<iface>="dhcp"``) or statically assigned one CIDR address with an
optional default gateway (``config_<iface>="192.168.1.5/24"`` +
``routes_<iface>="default via 192.168.1.1"``). Pure and CI-testable; the backend
does the privileged write.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass


@dataclass(slots=True)
class InterfaceConfig:
    iface: str
    method: str = "none"          # "dhcp" / "static" / "none" (unconfigured)
    address: str = ""             # CIDR, e.g. "192.168.1.5/24" (static only)
    gateway: str = ""             # default gateway IP (static only)


def valid_address(cidr: str) -> bool:
    try:
        ipaddress.ip_interface(cidr)
        return "/" in cidr
    except ValueError:
        return False


def valid_gateway(ip: str) -> bool:
    if not ip:
        return True  # gateway is optional
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def _assign_re(prefix: str, iface: str) -> re.Pattern:
    return re.compile(
        rf'^\s*{prefix}_{re.escape(iface)}\s*=\s*"?([^"\n#]*)"?\s*(?:#.*)?$'
    )


def parse_conf_net(text: str, iface: str) -> InterfaceConfig:
    """Parse the config for one interface out of /etc/conf.d/net."""
    cfg_re = _assign_re("config", iface)
    routes_re = _assign_re("routes", iface)
    config_val = ""
    routes_val = ""
    for line in text.splitlines():
        m = cfg_re.match(line)
        if m:
            config_val = m.group(1).strip()
        m = routes_re.match(line)
        if m:
            routes_val = m.group(1).strip()
    if not config_val:
        return InterfaceConfig(iface, "none")
    if config_val.lower() == "dhcp":
        return InterfaceConfig(iface, "dhcp")
    gateway = ""
    gw = re.search(r"default\s+via\s+(\S+)", routes_val)
    if gw:
        gateway = gw.group(1)
    return InterfaceConfig(iface, "static", address=config_val, gateway=gateway)


def render_conf_net(text: str, config: InterfaceConfig) -> str:
    """Return /etc/conf.d/net content with this interface's lines replaced."""
    cfg_re = _assign_re("config", config.iface)
    routes_re = _assign_re("routes", config.iface)
    kept = [
        line for line in text.splitlines()
        if not cfg_re.match(line) and not routes_re.match(line)
    ]
    if config.method == "dhcp":
        kept.append(f'config_{config.iface}="dhcp"')
    elif config.method == "static":
        kept.append(f'config_{config.iface}="{config.address}"')
        if config.gateway:
            kept.append(f'routes_{config.iface}="default via {config.gateway}"')
    body = "\n".join(kept).strip()
    return body + "\n" if body else ""
