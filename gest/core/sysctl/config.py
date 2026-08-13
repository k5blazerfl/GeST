"""Parse/validate/render the GeST sysctl.d drop-in — pure and CI-testable."""

from __future__ import annotations

import re

MARKER = "# Managed by GeST"
SYSCTL_DROPIN = "/etc/sysctl.d/10-gest.conf"

# A sysctl key: dotted/slashed lowercase path, e.g. net.ipv4.ip_forward or
# net/ipv4/ip_forward. Conservative — no whitespace or shell metacharacters.
_KEY_RE = re.compile(r"\A[a-z0-9][a-z0-9._/-]*\Z")


def valid_key(key: str) -> bool:
    return bool(_KEY_RE.match(key)) and len(key) <= 128


def valid_value(value: str) -> bool:
    # A single-line scalar; sysctl values never span lines and shouldn't carry a
    # comment marker into the drop-in.
    return value != "" and "\n" not in value and "#" not in value and len(value) <= 256


def valid_settings(settings: dict[str, str]) -> bool:
    return bool(settings) and all(
        valid_key(k) and valid_value(v) for k, v in settings.items())


def parse_conf(text: str) -> dict[str, str]:
    """Parse ``key = value`` lines (``=`` or whitespace separated) into a dict."""
    settings: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith((";", "#")):
            continue
        if "=" in stripped:
            key, _, value = stripped.partition("=")
        else:
            key, _, value = stripped.partition(" ")
        key, value = key.strip(), value.strip()
        if key and value:
            settings[key] = value
    return settings


def render_conf(settings: dict[str, str]) -> str:
    """Render the drop-in: header + one ``key = value`` per setting (sorted)."""
    lines = [MARKER]
    lines += [f"{key} = {settings[key]}" for key in sorted(settings)]
    return "\n".join(lines) + "\n"
