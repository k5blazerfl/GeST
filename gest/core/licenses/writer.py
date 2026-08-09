"""Build the :class:`ConfigWrite`\\ s that apply license changes.

Per-package acceptances edit ``package.license/gest`` one atom at a time
through the ``atomfile`` codec (preserving any other entries and comments); the
global ``ACCEPT_LICENSE`` is a make.conf variable. Both are handed to the
Portage ``WriteConfig`` RPC.
"""

from __future__ import annotations

from gest.core.makeconf import writer as makeconf_writer
from gest.core.portage import paths
from gest.core.portage.codec import atomfile
from gest.core.portage.write import ConfigWrite


def build_line(atom: str, licenses: list[str]) -> str:
    """The ``package.license`` line for ``atom`` (``""`` when no licenses)."""
    toks = [t for t in licenses if t]
    return f"{atom} {' '.join(toks)}" if toks else ""


def set_licenses(atom: str, licenses: list[str], *, path: str | None = None) -> ConfigWrite:
    """A :class:`ConfigWrite` setting ``atom``'s accepted licenses in gest.

    An empty ``licenses`` list removes the atom's line entirely.
    """
    target = path or paths.gest_fragment("license")
    try:
        with open(target, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = ""
    return ConfigWrite(target, atomfile.upsert(text, atom, build_line(atom, licenses)))


def set_accept_license(value: str, *, path: str | None = None) -> ConfigWrite:
    """A :class:`ConfigWrite` setting the global ``ACCEPT_LICENSE`` in make.conf."""
    return makeconf_writer.set_variable("ACCEPT_LICENSE", value, path=path)
