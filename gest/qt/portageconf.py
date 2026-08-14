"""Shared bridge to the unified Portage ``WriteConfig`` backend.

make.conf, binhost, and licenses all edit files under ``/etc/portage`` through
the *same* polkit-gated RPC: the core renders one or more
:class:`~gest.core.portage.write.ConfigWrite` values and hands them here. Unlike
the dedicated backends, ``write_config`` returns a bare ``bool``, so we wrap it
in the ``[ok, message]`` shape :func:`gest.qt.backend.run_backend` expects.
"""

from __future__ import annotations

from collections.abc import Sequence

from gest.core.portage.write import ConfigWrite
from gest.qt.backend import run_backend


def apply_writes(writes: Sequence[ConfigWrite]) -> tuple[bool, str]:
    """Apply ``writes`` atomically via the Portage backend (polkit-gated)."""

    async def run():
        from gest.core.portage.backend_client import PortageBackend

        backend = await PortageBackend().connect()
        try:
            ok = await backend.write_config(list(writes))
            return [bool(ok), "" if ok else "the backend rejected the write"]
        finally:
            await backend.close()

    return run_backend(run)


def setup_trust() -> tuple[bool, str]:
    """Run ``getuto`` to set up the binary-package trust keyring (polkit-gated)."""

    async def run():
        from gest.core.portage.backend_client import PortageBackend

        backend = await PortageBackend().connect()
        try:
            return await backend.setup_trust()
        finally:
            await backend.close()

    return run_backend(run)
