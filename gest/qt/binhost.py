"""Binhost module logic: pure label + bridges to the Portage backend."""

from __future__ import annotations

from gest.core.binhost.model import Binhost
from gest.core.binhost.reader import read_managed
from gest.core.binhost.writer import remove_host, set_feature, upsert_host, write_hosts
from gest.qt.portageconf import apply_writes, setup_trust


def host_label(host: Binhost) -> str:
    tag = "" if host.managed else " (external)"
    return f"{host.name}{tag} · {host.sync_uri or '—'}"


def save_host(host: Binhost) -> tuple[bool, str]:
    """Add or replace ``host`` in GeST's gest.conf and apply."""
    hosts = upsert_host(read_managed(), host)
    return apply_writes([write_hosts(hosts)])


def delete_host(name: str) -> tuple[bool, str]:
    """Remove the managed host named ``name`` and apply."""
    hosts = remove_host(read_managed(), name)
    return apply_writes([write_hosts(hosts)])


def set_feature_token(token: str, enabled: bool) -> tuple[bool, str]:
    """Toggle one FEATURES token (getbinpkg / signatures) in make.conf."""
    return apply_writes([set_feature(token, enabled)])


def run_setup_trust() -> tuple[bool, str]:
    """Run ``getuto`` once to set up the binary-package trust keyring."""
    return setup_trust()
