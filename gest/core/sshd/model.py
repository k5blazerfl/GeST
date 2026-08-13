"""The managed sshd_config settings and their defaults."""

from __future__ import annotations

from dataclasses import dataclass

# PermitRootLogin's allowed values (OpenSSH).
ROOT_LOGIN_VALUES = ("yes", "no", "prohibit-password", "forced-commands-only")


@dataclass(slots=True, frozen=True)
class SshdSettings:
    """The subset of sshd_config GeST manages.

    Values mirror OpenSSH's own defaults so a fresh read of a stock config
    reports what sshd would actually do, not blanks.
    """

    port: int = 22
    permit_root_login: str = "prohibit-password"
    password_authentication: bool = True
    pubkey_authentication: bool = True
    x11_forwarding: bool = False
    permit_empty_passwords: bool = False


# The default OpenSSH would use for each directive when it's absent from the file.
DEFAULTS = SshdSettings()
