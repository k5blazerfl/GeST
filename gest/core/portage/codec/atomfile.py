"""``package.*`` atom-keyed line grammar: parse, look up, and upsert.

Every ``/etc/portage/package.*`` drop-in is the same shape — one atom per line,
``cat/pkg token token…`` — used for ``package.use``, ``package.accept_keywords``,
``package.mask``, ``package.unmask``, and ``package.license``. This unifies the
per-atom line logic that previously lived in both ``core/software`` and the
backend, so the preview the user accepts and the file the backend writes can
never diverge.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AtomLine:
    atom: str
    tokens: list[str]


def parse(text: str) -> list[AtomLine]:
    """Every non-comment, non-blank line as an :class:`AtomLine`, in order."""
    out: list[AtomLine] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        out.append(AtomLine(parts[0], parts[1:]))
    return out


def line_for(text: str, atom: str) -> str:
    """The current line for ``atom`` (``""`` if none)."""
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and line.split()[0] == atom:
            return line
    return ""


def tokens_for(text: str, atom: str) -> list[str]:
    """The tokens following ``atom`` on its line (``[]`` if the atom is absent)."""
    line = line_for(text, atom)
    return line.split()[1:] if line else []


def upsert(text: str, atom: str, line: str) -> str:
    """Return ``text`` with ``atom``'s entry set to ``line``.

    Drops any existing line for ``atom`` and, when ``line`` is non-empty, appends
    it. Comment and blank lines are preserved in place; an empty ``line`` simply
    removes the atom. The result is newline-terminated, or ``""`` when empty.
    """
    kept: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            kept.append(raw)
            continue
        if stripped.split()[0] == atom:
            continue  # drop the old line for this atom
        kept.append(raw)
    if line:
        kept.append(line)
    body = "\n".join(kept).strip()
    return body + "\n" if body else ""
