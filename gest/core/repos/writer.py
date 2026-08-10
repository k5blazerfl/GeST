"""Build the :class:`ConfigWrite` that records which repos refresh on open.

The selection is persisted to GeST's own state file (see
:mod:`gest.core.repos.refresh`), handed to the Portage ``WriteConfig`` RPC
(``org.gentoo.gest.portage.configure``), which re-validates it and applies it
atomically as root. Nothing in ``repos.conf`` is touched.
"""

from __future__ import annotations

from collections.abc import Iterable

from gest.core.portage.write import ConfigWrite
from gest.core.repos import disabled, refresh


def set_refresh(names: Iterable[str], *, path: str | None = None) -> ConfigWrite:
    """A :class:`ConfigWrite` persisting exactly ``names`` to the state file.

    An empty selection renders to ``""``, which deletes the file — so turning
    off the last repository leaves no stray state behind.
    """
    target = path or refresh.state_path()
    return ConfigWrite(target, refresh.render(set(names)))


def set_disabled(repos: Iterable[disabled.DisabledRepo], *,
                 path: str | None = None) -> ConfigWrite:
    """A :class:`ConfigWrite` persisting the disabled-repos record.

    An empty list renders to ``""`` (deletes the file) — so re-enabling the last
    tracked repo leaves no stray state behind.
    """
    target = path or disabled.state_path()
    return ConfigWrite(target, disabled.render(list(repos)))
