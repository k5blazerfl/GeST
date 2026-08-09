"""Unprivileged reads for the licenses module.

Per-package acceptances come from ``/etc/portage/package.license`` — which may
be a directory of fragments or a single file — parsed with the shared
``atomfile`` codec. The global ``ACCEPT_LICENSE`` is read from make.conf. Only
entries in GeST's own ``package.license/gest`` fragment are ``managed``.
"""

from __future__ import annotations

import os

from gest.core.licenses.model import LicenseEntry
from gest.core.makeconf import reader as makeconf
from gest.core.portage import paths
from gest.core.portage.codec import atomfile

GEST_FRAGMENT = "gest"


def _entries(path: str, managed: bool) -> list[LicenseEntry]:
    try:
        with open(path, encoding="utf-8") as fh:
            rows = atomfile.parse(fh.read())
    except OSError:
        return []
    return [LicenseEntry(r.atom, list(r.tokens), managed) for r in rows]


def read_all(base: str | None = None) -> list[LicenseEntry]:
    """Every per-package acceptance; GeST-managed ones first, then by atom.

    Handles both forms of ``package.license``: a directory of fragment files
    (GeST's ``gest`` among them) or a single regular file.
    """
    base = base or paths.package_dir("license")
    out: list[LicenseEntry] = []
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            path = os.path.join(base, name)
            if name.startswith(".") or not os.path.isfile(path):
                continue
            out += _entries(path, managed=(name == GEST_FRAGMENT))
    elif os.path.isfile(base):
        out += _entries(base, managed=False)  # single-file form — not GeST-owned
    return sorted(out, key=lambda e: (not e.managed, e.atom))


def read_managed(path: str | None = None) -> list[LicenseEntry]:
    """Only the acceptances GeST owns (``package.license/gest``)."""
    return _entries(path or paths.gest_fragment("license"), managed=True)


def accept_license(path: str | None = None) -> str:
    """The global ``ACCEPT_LICENSE`` value from make.conf (``""`` if unset)."""
    for var in makeconf.read_makeconf(path):
        if var.name == "ACCEPT_LICENSE":
            return var.value
    return ""
