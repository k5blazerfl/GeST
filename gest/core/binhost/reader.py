"""Unprivileged reads for the binhost module.

Binhosts come from every ``binrepos.conf/*.conf`` fragment (parsed with the
shared INI codec); the ``FEATURES`` toggle state is read from make.conf. Only
hosts in GeST's own ``gest.conf`` are marked ``managed`` (editable here).
"""

from __future__ import annotations

import glob
import os

from gest.core.binhost.model import GETBINPKG, REQUIRE_SIGNATURE, Binhost, FeaturesState
from gest.core.makeconf import reader as makeconf
from gest.core.portage import paths
from gest.core.portage.codec import ini

GEST_FRAGMENT = "gest.conf"

_TRUE = {"true", "yes", "1", "on"}


def _host(name: str, entries: dict[str, str], managed: bool) -> Binhost:
    return Binhost(
        name=name,
        sync_uri=entries.get("sync-uri", ""),
        priority=entries.get("priority", ""),
        verify_signature=entries.get("verify-signature", "true").strip().lower() in _TRUE,
        location=entries.get("location", ""),
        managed=managed,
    )


def read_all(conf_dir: str | None = None) -> list[Binhost]:
    """Every configured binhost; GeST-managed ones (gest.conf) first."""
    conf_dir = conf_dir or paths.binrepos_conf_dir()
    hosts: list[Binhost] = []
    try:
        files = sorted(glob.glob(os.path.join(conf_dir, "*.conf")))
    except OSError:
        files = []
    for path in files:
        managed = os.path.basename(path) == GEST_FRAGMENT
        try:
            with open(path, encoding="utf-8") as fh:
                _defaults, sections = ini.parse(fh.read())
        except OSError:
            continue
        hosts += [_host(s.name, s.entries, managed) for s in sections]
    return sorted(hosts, key=lambda h: (not h.managed, h.name))


def read_managed(path: str | None = None) -> list[Binhost]:
    """Only the hosts GeST owns (``binrepos.conf/gest.conf``)."""
    path = path or paths.binhost_fragment()
    try:
        with open(path, encoding="utf-8") as fh:
            _defaults, sections = ini.parse(fh.read())
    except OSError:
        return []
    return [_host(s.name, s.entries, True) for s in sections]


def features_state(path: str | None = None) -> FeaturesState:
    """Whether getbinpkg / binpkg-request-signature are set in make.conf FEATURES."""
    tokens: set[str] = set()
    for var in makeconf.read_makeconf(path):
        if var.name == "FEATURES":
            tokens = set(var.value.split())
    return FeaturesState(
        getbinpkg=GETBINPKG in tokens,
        require_signature=REQUIRE_SIGNATURE in tokens,
    )
