"""Keyword acceptance and mask state — the package.accept_keywords / mask files.

Like USE flags, GeST manages one file per kind (``package.<kind>/gest``). Reads
happen as the user; writes go through the backend (polkit modify-config).

Two tri-state settings per package:

    keyword: default  → stable only (no entry)
             ~arch    → accept testing (``cat/pkg ~amd64``)
             **       → accept any keyword (``cat/pkg **``)

    mask:    default  → no entry
             masked   → entry in package.mask
             unmasked → entry in package.unmask
"""

from __future__ import annotations

import os

import portage

from gest.core.portage.codec import atomfile
from gest.core.portage.write import ConfigWrite

KW_DEFAULT, KW_TESTING, KW_ANY = "default", "~arch", "**"
MASK_DEFAULT, MASKED, UNMASKED = "default", "masked", "unmasked"


def arch() -> str:
    return portage.settings["ARCH"]


def gest_path(kind: str) -> str:
    return os.path.join(
        portage.settings["PORTAGE_CONFIGROOT"],
        "etc", "portage", f"package.{kind}", "gest",
    )


def read_line(kind: str, cp: str) -> str:
    """The current package.<kind>/gest line for ``cp`` ("" if none)."""
    try:
        with open(gest_path(kind), encoding="utf-8") as fh:
            return atomfile.line_for(fh.read(), cp)
    except OSError:
        return ""


def keyword_state(cp: str) -> str:
    line = read_line("accept_keywords", cp)
    if not line:
        return KW_DEFAULT
    return KW_ANY if "**" in line.split()[1:] else KW_TESTING


def mask_state(cp: str) -> str:
    if read_line("mask", cp):
        return MASKED
    if read_line("unmask", cp):
        return UNMASKED
    return MASK_DEFAULT


def keyword_line(cp: str, state: str) -> str:
    if state == KW_TESTING:
        return f"{cp} ~{arch()}"
    if state == KW_ANY:
        return f"{cp} **"
    return ""


def desired_lines(cp: str, kw: str, mask: str) -> dict[str, str]:
    """The intended package.<kind>/gest line for each managed kind."""
    return {
        "accept_keywords": keyword_line(cp, kw),
        "mask": cp if mask == MASKED else "",
        "unmask": cp if mask == UNMASKED else "",
    }


def changed_writes(cp: str, kw: str, mask: str) -> list[tuple[str, str]]:
    """(kind, line) writes needed to reach the desired states (only changes)."""
    writes = []
    for kind, line in desired_lines(cp, kw, mask).items():
        if line != read_line(kind, cp):
            writes.append((kind, line))
    return writes


def writes_for(cp: str, kw: str, mask: str) -> list[ConfigWrite]:
    """A :class:`ConfigWrite` per package.<kind>/gest file that must change."""
    out: list[ConfigWrite] = []
    for kind, line in changed_writes(cp, kw, mask):
        target = gest_path(kind)
        try:
            with open(target, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            text = ""
        out.append(ConfigWrite(target, atomfile.upsert(text, cp, line)))
    return out
