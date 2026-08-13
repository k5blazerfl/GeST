"""Detect which firewall backend a host is actually running (unprivileged).

GeST ships two firewall modules — the nftables one and the firewalld one — but
the menu exposes a single "Firewall" entry. This module works out, from cheap
unprivileged probes, which backend is live so the menu can route to the right
one (or offer a choice when both or neither are present).

Everything here is pure given an injectable ``runner`` (a callable returning
``(exit_code, stdout)``), so the routing logic is fully CI-testable without a
live firewall: construct a :class:`FirewallStatus` directly, or pass a fake
runner to :func:`detect`.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from gest.core.firewall import reader as nft_reader

Runner = Callable[[list[str]], tuple[int, str]]


def _default_runner(argv: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True)
        return proc.returncode, proc.stdout
    except OSError:
        return 127, ""


def firewalld_installed(runner: Runner | None = None) -> bool:
    """True when the ``firewall-cmd`` client is on PATH (firewalld installed)."""
    return shutil.which("firewall-cmd") is not None


def firewalld_running(runner: Runner | None = None) -> bool:
    """True when ``firewall-cmd --state`` reports a running daemon.

    ``--state`` is the reliable unprivileged liveness probe: it exits 0 and
    prints ``running`` when firewalld is up, and exits non-zero otherwise.
    """
    run = runner or _default_runner
    code, out = run(["firewall-cmd", "--state"])
    return code == 0 and "running" in out.lower()


def nftables_installed(runner: Runner | None = None) -> bool:
    """True when the ``nft`` binary is on PATH (nftables installed)."""
    return shutil.which("nft") is not None


def nftables_active(runner: Runner | None = None) -> bool:
    """Best-effort: True when GeST manages the on-disk nftables ruleset.

    We key off the GeST-managed ``/etc/nftables.nft`` (via the nftables module's
    own :func:`~gest.core.firewall.reader.is_managed`) rather than the mere
    presence of the ``nft`` tool. firewalld itself drives the nftables kernel
    backend, so a running-firewalld host almost always has ``nft`` installed —
    treating tool presence as "nftables active" would misreport every firewalld
    system as "both". The live ``nft list ruleset`` needs root, so we can't probe
    the kernel unprivileged; the managed-file signal is the reliable one.
    """
    return nft_reader.is_managed()


@dataclass(slots=True, frozen=True)
class FirewallStatus:
    """A snapshot of both firewall backends' presence/liveness.

    ``active`` reduces the four signals to the single backend the menu should
    open: firewalld when it is running, the nftables module when it manages the
    host, ``"both"`` when both look live (let the user choose), or ``"none"``.
    """

    firewalld_installed: bool = False
    firewalld_running: bool = False
    nftables_installed: bool = False
    nftables_active: bool = False

    @property
    def active(self) -> str:
        if self.firewalld_running and self.nftables_active:
            return "both"
        if self.firewalld_running:
            return "firewalld"
        if self.nftables_active:
            return "nftables"
        return "none"


def detect(runner: Runner | None = None) -> FirewallStatus:
    """Probe both backends and return a :class:`FirewallStatus`."""
    run = runner or _default_runner
    return FirewallStatus(
        firewalld_installed=firewalld_installed(run),
        firewalld_running=firewalld_running(run),
        nftables_installed=nftables_installed(run),
        nftables_active=nftables_active(run),
    )
