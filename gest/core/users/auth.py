"""Report which authentication back-ends resolve local accounts (unprivileged).

Parsed from ``/etc/nsswitch.conf``: which providers beyond ``files`` appear on
the ``passwd:`` line (SSSD, LDAP, NIS, Winbind/Samba). This is a read-only
status view — GeST does not configure these providers. It answers the same
question as YaST's "Authentication Settings" tab: is anything but local files
in use?
"""

from __future__ import annotations

from dataclasses import dataclass

NSSWITCH = "/etc/nsswitch.conf"

# Display name -> nsswitch tokens that indicate it is in use. "compat" is
# deliberately not treated as NIS: it is the stock default and does not by
# itself mean NIS is configured.
_PROVIDERS: list[tuple[str, frozenset[str]]] = [
    ("SSSD", frozenset({"sss"})),
    ("LDAP", frozenset({"ldap"})),
    ("NIS", frozenset({"nis"})),
    ("Samba / Winbind", frozenset({"winbind"})),
]


@dataclass(slots=True)
class AuthProvider:
    name: str
    configured: bool


def db_sources(text: str, db: str) -> list[str]:
    """Tokens listed for an nsswitch database, e.g. ``db="passwd"``."""
    prefix = f"{db}:"
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(prefix):
            return s[len(prefix):].split()
    return []


def read_providers(path: str = NSSWITCH) -> list[AuthProvider]:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = ""
    sources = set(db_sources(text, "passwd")) | set(db_sources(text, "group"))
    return [AuthProvider(name, bool(tokens & sources)) for name, tokens in _PROVIDERS]


def read_lines(path: str = NSSWITCH) -> dict[str, str]:
    """The raw passwd/group source lists, for display (``{db: "files sss"}``)."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = ""
    return {db: " ".join(db_sources(text, db)) for db in ("passwd", "group")}
