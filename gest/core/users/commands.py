"""Pure, validated argv builders for user/group mutations.

Kept dependency-free so the root backend and the tests share one validated
command shape — a bus caller can never smuggle in extra arguments. Every builder
raises ValueError on anything that doesn't match the strict name/path rules.
"""

from __future__ import annotations

import re

# shadow-utils NAME_REGEX: start with a lowercase letter or underscore; a
# trailing '$' is allowed (Samba machine accounts).
_NAME_RE = re.compile(r"\A[a-z_][a-z0-9_-]*\$?\Z")
_PATH_RE = re.compile(r"\A/[^\0\n]*\Z")


def valid_name(name: str) -> bool:
    return bool(_NAME_RE.match(name)) and len(name) <= 32


def _require_name(name: str) -> None:
    if not valid_name(name):
        raise ValueError(f"invalid name: {name!r}")


def _require_path(path: str) -> None:
    if not _PATH_RE.match(path):
        raise ValueError(f"invalid path: {path!r}")


def _split_groups(groups: str) -> list[str]:
    names = [g.strip() for g in groups.split(",") if g.strip()]
    for g in names:
        _require_name(g)
    return names


def _require_text(value: str, label: str) -> None:
    if "\n" in value or ":" in value:
        raise ValueError(f"invalid {label}")


def useradd_argv(
    name: str,
    *,
    comment: str = "",
    shell: str = "",
    home: str = "",
    groups: str = "",
    system: bool = False,
    useradd: str = "useradd",
) -> list[str]:
    _require_name(name)
    argv = [useradd]
    argv.append("--system" if system else "--create-home")
    if comment:
        _require_text(comment, "comment")
        argv += ["--comment", comment]
    if shell:
        _require_path(shell)
        argv += ["--shell", shell]
    if home:
        _require_path(home)
        argv += ["--home-dir", home]
    if groups:
        argv += ["--groups", ",".join(_split_groups(groups))]
    argv.append(name)
    return argv


def usermod_argv(
    name: str,
    *,
    comment: str | None = None,
    shell: str | None = None,
    groups: str | None = None,
    usermod: str = "usermod",
) -> list[str]:
    _require_name(name)
    argv = [usermod]
    if comment is not None and comment != "":
        _require_text(comment, "comment")
        argv += ["--comment", comment]
    if shell is not None and shell != "":
        _require_path(shell)
        argv += ["--shell", shell]
    if groups is not None and groups != "":
        argv += ["--groups", ",".join(_split_groups(groups))]
    if len(argv) == 1:
        raise ValueError("no modifications requested")
    argv.append(name)
    return argv


def userdel_argv(name: str, *, remove_home: bool = False, userdel: str = "userdel") -> list[str]:
    _require_name(name)
    argv = [userdel]
    if remove_home:
        argv.append("--remove")
    argv.append(name)
    return argv


def groupadd_argv(name: str, *, system: bool = False, groupadd: str = "groupadd") -> list[str]:
    _require_name(name)
    argv = [groupadd]
    if system:
        argv.append("--system")
    argv.append(name)
    return argv


def groupdel_argv(name: str, *, groupdel: str = "groupdel") -> list[str]:
    _require_name(name)
    return [groupdel, name]


def chpasswd_input(
    name: str, password: str, *, chpasswd: str = "chpasswd"
) -> tuple[list[str], str]:
    """Build (argv, stdin) for setting a password via chpasswd.

    The password is fed on stdin (``name:password``) so it never lands in argv
    or the process list. A newline would let a caller inject a second entry, so
    it is rejected; the password must be non-empty.
    """
    _require_name(name)
    if not password:
        raise ValueError("empty password")
    if "\n" in password or "\r" in password:
        raise ValueError("invalid password")
    return [chpasswd], f"{name}:{password}\n"


def gpasswd_argv(group: str, user: str, *, add: bool, gpasswd: str = "gpasswd") -> list[str]:
    """Add or remove ``user`` from ``group`` via gpasswd -a/-d."""
    _require_name(group)
    _require_name(user)
    return [gpasswd, "-a" if add else "-d", user, group]
