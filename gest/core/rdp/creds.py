"""Gangway credentials via the Secret Service (libsecret's ``secret-tool``).

The password for a profile lives in the Keychain — ``helm-keyringd`` on a HeDE
box, or whatever Secret Service provider is running. We talk to it through
``secret-tool`` so Gangway needs no dbus dependency of its own. The argv builders
are pure/testable; :func:`store`/:func:`lookup` are the thin subprocess wrappers.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping

SECRET_TOOL = "secret-tool"


def store_argv(attributes: Mapping[str, str], label: str) -> list[str]:
    argv = [SECRET_TOOL, "store", f"--label={label}"]
    for key, value in attributes.items():
        argv += [key, value]
    return argv


def lookup_argv(attributes: Mapping[str, str]) -> list[str]:
    argv = [SECRET_TOOL, "lookup"]
    for key, value in attributes.items():
        argv += [key, value]
    return argv


def clear_argv(attributes: Mapping[str, str]) -> list[str]:
    argv = [SECRET_TOOL, "clear"]
    for key, value in attributes.items():
        argv += [key, value]
    return argv


def store(attributes: Mapping[str, str], label: str, password: str) -> bool:
    """Store ``password`` in the keychain (``secret-tool`` reads it from stdin)."""
    result = subprocess.run(store_argv(attributes, label), input=password.encode(),
                            capture_output=True)
    return result.returncode == 0


def lookup(attributes: Mapping[str, str]) -> str | None:
    """Fetch a stored password, or ``None`` if not found / no provider."""
    try:
        result = subprocess.run(lookup_argv(attributes), capture_output=True)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    # secret-tool prints the secret with no trailing newline of its own.
    return result.stdout.decode("utf-8", "surrogateescape").rstrip("\n")
