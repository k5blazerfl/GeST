"""Licenses module logic: pure label + bridges to the Portage backend."""

from __future__ import annotations

from gest.core.licenses.model import LicenseEntry
from gest.core.licenses.writer import set_accept_license, set_licenses
from gest.qt.portageconf import apply_writes


def entry_label(entry: LicenseEntry) -> str:
    tag = "" if entry.managed else " (external)"
    return f"{entry.atom}{tag} → {' '.join(entry.licenses) or '(none)'}"


def set_atom_licenses(atom: str, licenses: list[str]) -> tuple[bool, str]:
    """Set (or, with an empty list, clear) an atom's accepted licenses."""
    atom = atom.strip()
    if not atom:
        return (False, "no package atom given")
    toks = [t for t in (s.strip() for s in licenses) if t]
    return apply_writes([set_licenses(atom, toks)])


def set_global_accept(value: str) -> tuple[bool, str]:
    """Set the global ``ACCEPT_LICENSE`` in make.conf."""
    return apply_writes([set_accept_license(value)])
