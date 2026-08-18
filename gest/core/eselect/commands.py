"""Pure, validated argv builder for eselect target switching."""

from __future__ import annotations

import re

_MODULE_RE = re.compile(r"\A[a-z][a-z0-9_-]*\Z")
# A profile/target NAME: `eselect profile set` accepts a path like
# `default/linux/amd64/23.0/systemd` as well as a list number.
_NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._/-]*\Z")


def valid_module(name: str) -> bool:
    return bool(_MODULE_RE.match(name))


def set_argv(module: str, target: str | int, *, eselect: str = "eselect") -> list[str]:
    """Build ``eselect <module> set <target>``; ``target`` is a positive list number
    or a target NAME (e.g. a profile path). Raises ValueError on bad input."""
    if not valid_module(module):
        raise ValueError(f"invalid eselect module: {module!r}")
    t = str(target)
    is_number = t.isdigit() and int(t) >= 1
    is_name = bool(_NAME_RE.match(t)) and ".." not in t
    if not (is_number or is_name):
        raise ValueError(f"invalid target: {target!r}")
    return [eselect, module, "set", t]
