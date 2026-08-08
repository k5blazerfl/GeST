"""Read/validate the system hostname (OpenRC: /etc/conf.d/hostname)."""

from __future__ import annotations

import re
import socket

# One or more DNS labels (RFC 1123): alphanumeric, hyphens inside, dots between.
_HOSTNAME_RE = re.compile(
    r"\A[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\Z"
)
_CONF_RE = re.compile(r'^\s*hostname\s*=\s*"?([^"\n#]+?)"?\s*(?:#.*)?$', re.MULTILINE)


def valid_hostname(name: str) -> bool:
    return bool(name) and len(name) <= 253 and bool(_HOSTNAME_RE.match(name))


def parse_conf_hostname(text: str) -> str:
    """Pull the hostname out of an OpenRC /etc/conf.d/hostname file."""
    match = _CONF_RE.search(text)
    return match.group(1).strip() if match else ""


def current_hostname(conf: str = "/etc/conf.d/hostname") -> str:
    try:
        with open(conf, encoding="utf-8") as fh:
            name = parse_conf_hostname(fh.read())
        if name:
            return name
    except OSError:
        pass
    return socket.gethostname()
