"""Parse the managed directives out of sshd_config, and upsert them back.

sshd_config is a ``Keyword value`` file (whitespace-separated, ``#`` comments,
and for most keywords the *first* active occurrence wins). We only ever touch the
handful of directives in :class:`SshdSettings`: parsing reads the first active
value (falling back to OpenSSH's default), and applying replaces that first
active line in place — or appends one — so every other line, comment and Match
block is preserved. All pure and CI-testable.
"""

from __future__ import annotations

import re

from gest.core.sshd.model import DEFAULTS, ROOT_LOGIN_VALUES, SshdSettings

# sshd_config keyword for each SshdSettings field, in a stable render order.
_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("Port", "port"),
    ("PermitRootLogin", "permit_root_login"),
    ("PasswordAuthentication", "password_authentication"),
    ("PubkeyAuthentication", "pubkey_authentication"),
    ("X11Forwarding", "x11_forwarding"),
    ("PermitEmptyPasswords", "permit_empty_passwords"),
)


def valid_port(port: int) -> bool:
    return isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535


def valid_root_login(value: str) -> bool:
    return value in ROOT_LOGIN_VALUES


def valid_settings(settings: SshdSettings) -> bool:
    return valid_port(settings.port) and valid_root_login(settings.permit_root_login)


def _active_re(keyword: str) -> re.Pattern[str]:
    # An active (non-comment) directive line for `keyword`, case-insensitive.
    return re.compile(rf"(?im)^[ \t]*{keyword}[ \t]+(\S.*?)[ \t]*$")


def _first_value(text: str, keyword: str) -> str | None:
    match = _active_re(keyword).search(text)
    if not match:
        return None
    # Directives take a single token for everything we manage.
    return match.group(1).split()[0]


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() == "yes"


def parse_settings(text: str) -> SshdSettings:
    """Read the managed directives from ``text``, using OpenSSH defaults if unset."""
    port_val = _first_value(text, "Port")
    port = int(port_val) if port_val and port_val.isdigit() else DEFAULTS.port
    root = _first_value(text, "PermitRootLogin")
    if root not in ROOT_LOGIN_VALUES:
        root = DEFAULTS.permit_root_login
    return SshdSettings(
        port=port,
        permit_root_login=root,
        password_authentication=_to_bool(
            _first_value(text, "PasswordAuthentication"), DEFAULTS.password_authentication),
        pubkey_authentication=_to_bool(
            _first_value(text, "PubkeyAuthentication"), DEFAULTS.pubkey_authentication),
        x11_forwarding=_to_bool(
            _first_value(text, "X11Forwarding"), DEFAULTS.x11_forwarding),
        permit_empty_passwords=_to_bool(
            _first_value(text, "PermitEmptyPasswords"), DEFAULTS.permit_empty_passwords),
    )


def _render_value(field: str, settings: SshdSettings) -> str:
    value = getattr(settings, field)
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _upsert(text: str, keyword: str, value: str) -> str:
    """Replace the first active `keyword` line with `keyword value`, else append."""
    line = f"{keyword} {value}"
    pattern = _active_re(keyword)
    if pattern.search(text):
        return pattern.sub(lambda _m: line, text, count=1)
    sep = "" if text == "" or text.endswith("\n") else "\n"
    return text + sep + line + "\n"


def apply_settings(text: str, settings: SshdSettings) -> str:
    """Upsert every managed directive from ``settings`` into ``text``."""
    for keyword, field in _KEYWORDS:
        text = _upsert(text, keyword, _render_value(field, settings))
    return text
