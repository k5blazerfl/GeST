"""Read /etc/portage/make.conf.

Parsing and format-preserving rendering live in the shared shell codec
(:mod:`gest.core.portage.codec.shell`); this module is the thin, unprivileged
I/O layer over it. Writes go through the Portage backend (see
:mod:`gest.core.makeconf.writer`).
"""

from __future__ import annotations

from gest.core.portage import paths
from gest.core.portage.codec.shell import (  # re-exported for callers
    Var,
    assignments,
    render,
    valid_name,
    valid_value,
    variables,
)

__all__ = [
    "MAKE_CONF",
    "Var",
    "assignments",
    "read_makeconf",
    "render",
    "valid_name",
    "valid_value",
    "variables",
]

# Kept for callers that reference a default path; the effective path honours
# PORTAGE_CONFIGROOT via :func:`gest.core.portage.paths.make_conf`.
MAKE_CONF = "/etc/portage/make.conf"


def read_makeconf(path: str | None = None) -> list[Var]:
    """The effective variables in make.conf (``[]`` if it can't be read)."""
    try:
        with open(path or paths.make_conf(), encoding="utf-8") as fh:
            return variables(fh.read())
    except OSError:
        return []
