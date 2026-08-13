"""Read the persisted nftables config (unprivileged) and detect the tool.

The active kernel ruleset (`nft list ruleset`) needs privilege, so the reader
works from the on-disk ``/etc/nftables.nft`` GeST manages — enough to show and
edit the current policy. Applying it (privileged) lives in the backend.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from gest.core.firewall import nft
from gest.core.firewall.model import FirewallPolicy

Runner = Callable[[list[str]], tuple[int, str]]


def read_config(path: str = nft.NFT_PATH) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def current_policy(path: str = nft.NFT_PATH) -> FirewallPolicy | None:
    """The GeST-managed policy in ``path``, or ``None`` if absent/unmanaged."""
    return nft.parse_ruleset(read_config(path))


def is_managed(path: str = nft.NFT_PATH) -> bool:
    """True if ``path`` exists and is a GeST-rendered ruleset."""
    return current_policy(path) is not None


def _default_runner(argv: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True)
        return proc.returncode, proc.stdout
    except OSError:
        return 127, ""


def nft_available(runner: Runner | None = None) -> bool:
    """True if the `nft` binary is present and runnable."""
    run = runner or _default_runner
    code, _out = run(["nft", "--version"])
    return code == 0
