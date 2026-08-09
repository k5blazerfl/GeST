"""Build the :class:`ConfigWrite` that sets a make.conf variable.

Reading make.conf is unprivileged, so the full new contents are rendered here
(format-preserving) and handed to the Portage backend, which re-validates and
writes them atomically. Rendering here also lets the UI preview the exact diff.
"""

from __future__ import annotations

from gest.core.portage import paths
from gest.core.portage.codec import shell
from gest.core.portage.write import ConfigWrite


def set_variable(name: str, value: str, *, path: str | None = None) -> ConfigWrite:
    """A :class:`ConfigWrite` that sets ``name=value`` in make.conf.

    Reads the current file (unprivileged) and renders the new contents with the
    variable's effective assignment replaced in place, or appended if absent.
    """
    target = path or paths.make_conf()
    try:
        with open(target, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = ""
    return ConfigWrite(target, shell.render(text, name, value))
