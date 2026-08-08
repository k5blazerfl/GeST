"""Read eselect modules and targets (unprivileged)."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable

from gest.core.eselect.model import Module, Target

Runner = Callable[[list[str]], str]

# Built-in eselect modules that aren't a settable list of targets.
_SKIP = {"help", "usage", "version"}
_MODULE_RE = re.compile(r"^  (\S+)\s{2,}(.+)$")
_TARGET_RE = re.compile(r"^\s*\[\s*(\d*)\s*\]\s+(.*)$")


def parse_modules(text: str) -> list[Module]:
    """Parse `eselect modules list` output."""
    modules: list[Module] = []
    for line in text.splitlines():
        m = _MODULE_RE.match(line)
        if not m:
            continue
        name, desc = m.group(1), m.group(2).strip()
        if name in _SKIP:
            continue
        modules.append(Module(name, desc))
    return modules


def parse_targets(text: str) -> list[Target]:
    """Parse `eselect <module> list` output into numbered targets.

    Entries without a number (e.g. ``[ ]  (free form)``) are skipped since they
    can't be selected by number.
    """
    targets: list[Target] = []
    for line in text.splitlines():
        m = _TARGET_RE.match(line)
        if not m or not m.group(1):
            continue
        number = int(m.group(1))
        rest = m.group(2).rstrip()
        current = rest.endswith("*")
        name = rest[:-1].rstrip() if current else rest
        targets.append(Target(number, name, current))
    return targets


def _default_runner(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True).stdout
    except OSError:
        return ""


def list_modules(runner: Runner | None = None) -> list[Module]:
    run = runner or _default_runner
    return parse_modules(run(["eselect", "modules", "list"]))


def list_targets(module: str, runner: Runner | None = None) -> list[Target]:
    run = runner or _default_runner
    return parse_targets(run(["eselect", module, "list"]))
