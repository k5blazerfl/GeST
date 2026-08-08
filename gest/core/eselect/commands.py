"""Pure, validated argv builder for eselect target switching."""

from __future__ import annotations

import re

_MODULE_RE = re.compile(r"\A[a-z][a-z0-9_-]*\Z")


def valid_module(name: str) -> bool:
    return bool(_MODULE_RE.match(name))


def set_argv(module: str, target: str | int, *, eselect: str = "eselect") -> list[str]:
    """Build ``eselect <module> set <n>``; raise ValueError on bad input."""
    if not valid_module(module):
        raise ValueError(f"invalid eselect module: {module!r}")
    number = str(target)
    if not number.isdigit() or int(number) < 1:
        raise ValueError(f"invalid target: {target!r}")
    return [eselect, module, "set", number]
