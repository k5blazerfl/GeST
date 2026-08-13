"""Parse/validate/render the GeST env.d drop-in — pure and CI-testable."""

from __future__ import annotations

import re

MARKER = "# Managed by GeST"
ENVD_DROPIN = "/etc/env.d/99gest"

# A shell-style environment variable name.
_NAME_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")
# A value line for VAR=... or VAR="...".
_ASSIGN_RE = re.compile(r'\A([A-Za-z_][A-Za-z0-9_]*)=(?:"([^"]*)"|(\S*))\s*\Z')


def valid_name(name: str) -> bool:
    return bool(_NAME_RE.match(name)) and len(name) <= 128


def valid_value(value: str) -> bool:
    # Single line, no embedded double-quote or comment marker (we wrap in quotes).
    return "\n" not in value and '"' not in value and "#" not in value and len(value) <= 512


def valid_vars(variables: dict[str, str]) -> bool:
    return bool(variables) and all(
        valid_name(k) and valid_value(v) for k, v in variables.items())


def parse_conf(text: str) -> dict[str, str]:
    """Parse ``VAR=value`` / ``VAR="value"`` lines into a dict."""
    variables: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ASSIGN_RE.match(stripped)
        if match:
            name = match.group(1)
            value = match.group(2) if match.group(2) is not None else match.group(3)
            variables[name] = value
    return variables


def render_conf(variables: dict[str, str]) -> str:
    """Render the drop-in: header + one ``VAR="value"`` per variable (sorted)."""
    lines = [MARKER]
    lines += [f'{name}="{variables[name]}"' for name in sorted(variables)]
    return "\n".join(lines) + "\n"
