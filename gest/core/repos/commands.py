"""Pure, validated argv builders for `eselect repository` mutations."""

from __future__ import annotations

import re

_NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_TYPE_RE = re.compile(r"\A[a-z][a-z0-9+-]*\Z")


def valid_name(name: str) -> bool:
    return bool(_NAME_RE.match(name)) and len(name) <= 64


def valid_type(sync_type: str) -> bool:
    return bool(_TYPE_RE.match(sync_type))


def valid_uri(uri: str) -> bool:
    return bool(uri) and not re.search(r"[\s\0]", uri) and len(uri) <= 2048


def _require_name(name: str) -> None:
    if not valid_name(name):
        raise ValueError(f"invalid repository name: {name!r}")


def enable_argv(name: str, *, eselect: str = "eselect") -> list[str]:
    _require_name(name)
    return [eselect, "repository", "enable", name]


def disable_argv(name: str, *, eselect: str = "eselect") -> list[str]:
    _require_name(name)
    return [eselect, "repository", "disable", "-f", name]


def remove_argv(name: str, *, eselect: str = "eselect") -> list[str]:
    _require_name(name)
    return [eselect, "repository", "remove", "-f", name]


def add_argv(name: str, sync_type: str, uri: str, *, eselect: str = "eselect") -> list[str]:
    _require_name(name)
    if not valid_type(sync_type):
        raise ValueError(f"invalid sync type: {sync_type!r}")
    if not valid_uri(uri):
        raise ValueError(f"invalid sync uri: {uri!r}")
    return [eselect, "repository", "add", name, sync_type, uri]
