"""Pure argv builders for the nftables tool. No I/O; CI-testable."""

from __future__ import annotations


def nft_check_argv(path: str, *, nft: str = "nft") -> list[str]:
    """Dry-run: parse+validate a ruleset file without loading it (`nft -c -f`)."""
    return [nft, "-c", "-f", path]


def nft_load_argv(path: str, *, nft: str = "nft") -> list[str]:
    """Load (apply) a ruleset file into the kernel (`nft -f`)."""
    return [nft, "-f", path]


def nft_list_argv(*, nft: str = "nft") -> list[str]:
    """List the active ruleset (`nft list ruleset`) — needs privilege to run."""
    return [nft, "list", "ruleset"]


def nft_flush_argv(*, nft: str = "nft") -> list[str]:
    """Flush the entire active ruleset (`nft flush ruleset`)."""
    return [nft, "flush", "ruleset"]
