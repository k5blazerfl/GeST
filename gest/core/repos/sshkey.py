"""Root SSH deploy-key helpers for syncing private git repositories.

A private GitHub ebuild overlay is reached over SSH, and Portage runs the sync
as root — so root needs a key GitHub accepts as a deploy key. This is the pure,
argv-building side (CI-testable); the backend (:mod:`gest.backend.ssh`) runs
these as root and reads back the public key to show the user, who pastes it into
the repo's Settings → Deploy keys.

An ed25519 key with no passphrase is used: deploy keys are read-only and the
sync is non-interactive, so a passphrase would just break automated syncs.
"""

from __future__ import annotations

SSH_DIR = "/root/.ssh"
KEY_PATH = "/root/.ssh/id_ed25519"
PUB_PATH = KEY_PATH + ".pub"
KNOWN_HOSTS = "/root/.ssh/known_hosts"

# The host a GitHub overlay syncs from (git@github.com:…).
GITHUB_HOST = "github.com"


def default_comment(hostname: str) -> str:
    """A recognisable comment so the key is easy to spot in GitHub's deploy-key
    list (``gest-deploy@<this-machine>``)."""
    host = (hostname or "gentoo").strip() or "gentoo"
    return f"gest-deploy@{host}"


def keygen_argv(path: str = KEY_PATH, comment: str = "gest-deploy") -> list[str]:
    """``ssh-keygen`` for a passphraseless ed25519 key at ``path``."""
    return ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", path, "-C", comment]


def keyscan_argv(host: str = GITHUB_HOST) -> list[str]:
    """``ssh-keyscan`` to fetch a host's keys for known_hosts (stdout only)."""
    return ["ssh-keyscan", "-t", "rsa,ecdsa,ed25519", host]
