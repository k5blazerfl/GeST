"""Parse and re-render /etc/portage/make.conf assignments (raw, format-preserving)."""

from __future__ import annotations

import re
from dataclasses import dataclass

MAKE_CONF = "/etc/portage/make.conf"

_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_NAME_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")


@dataclass(slots=True)
class Var:
    name: str
    value: str


def valid_name(name: str) -> bool:
    return bool(_NAME_RE.match(name))


def valid_value(value: str) -> bool:
    """Reject values that would break the ``NAME="value"`` line or run commands.

    ``${VAR}`` parameter references are allowed (common in make.conf); command
    substitution (backticks / ``$(``) and structural characters are not.
    """
    if "\n" in value or "\0" in value or '"' in value or "`" in value:
        return False
    return "$(" not in value


def _find_close(text: str, quote: str) -> int | None:
    i = 0
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i
        i += 1
    return None


def _read_value(lines: list[str], start: int) -> tuple[str, int]:
    """Return (collapsed value, last line index) for the assignment at ``start``."""
    raw = lines[start]
    after = raw[raw.index("=") + 1:]
    end = start
    if after[:1] in ('"', "'"):
        quote = after[0]
        chunks: list[str] = []
        cur = after[1:]
        while True:
            idx = _find_close(cur, quote)
            if idx is not None:
                chunks.append(cur[:idx])
                break
            chunks.append(cur.rstrip().rstrip("\\"))
            end += 1
            if end >= len(lines):
                break
            cur = lines[end]
        value = " ".join(chunks)
    else:
        parts = [after]
        while parts[-1].rstrip().endswith("\\"):
            parts[-1] = parts[-1].rstrip()[:-1]
            end += 1
            if end >= len(lines):
                break
            parts.append(lines[end])
        value = " ".join(parts)
    return re.sub(r"\s+", " ", value).strip(), end


def _assignments(text: str) -> list[tuple[str, str, int, int]]:
    lines = text.split("\n")
    out: list[tuple[str, str, int, int]] = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s or s.startswith("#") or "=" not in lines[i]:
            i += 1
            continue
        m = _ASSIGN_RE.match(lines[i])
        if not m:
            i += 1
            continue
        value, end = _read_value(lines, i)
        out.append((m.group(1), value, i, end))
        i = end + 1
    return out


def variables(text: str) -> list[Var]:
    """Effective variables (later assignments win), in first-seen order."""
    order: list[str] = []
    values: dict[str, str] = {}
    for name, value, _s, _e in _assignments(text):
        if name not in values:
            order.append(name)
        values[name] = value
    return [Var(name, values[name]) for name in order]


def render(text: str, name: str, value: str) -> str:
    """Return make.conf text with ``name`` set to ``value`` (replacing its last
    assignment in place, or appending it if absent). Everything else is kept."""
    lines = text.split("\n")
    assigns = [a for a in _assignments(text) if a[0] == name]
    new_line = f'{name}="{value}"'
    if assigns:
        _n, _v, start, end = assigns[-1]  # replace the effective (last) one
        lines[start:end + 1] = [new_line]
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(new_line)
    return "\n".join(lines)


def read_makeconf(path: str = MAKE_CONF) -> list[Var]:
    try:
        with open(path, encoding="utf-8") as fh:
            return variables(fh.read())
    except OSError:
        return []
