"""Render and parse sudo/doas escalation policy — pure and CI-testable.

sudo is written as an isolated drop-in file; doas is managed as a delimited block
inside /etc/doas.conf so unrelated rules survive. Every render is reconstructable
by the matching parser, so the module can read back what it wrote.
"""

from __future__ import annotations

import re

from gest.core.privilege.model import (
    DOAS_BEGIN,
    DOAS_END,
    EscalationPolicy,
)

MARKER = "# Managed by GeST"

# A Unix group name (what `groupadd` accepts): a letter/underscore start, then
# letters, digits, underscore or hyphen.
_GROUP_RE = re.compile(r"\A[a-z_][a-z0-9_-]*\Z")
_SUDO_RE = re.compile(r"\A%(?P<group>\S+)\s+ALL=\(ALL:ALL\)\s+(?P<nopw>NOPASSWD:\s+)?ALL\s*\Z")


def valid_group(group: str) -> bool:
    return bool(_GROUP_RE.match(group)) and len(group) <= 32


# --- sudo (drop-in file) ----------------------------------------------------

def render_sudoers(policy: EscalationPolicy) -> str:
    """The full content of the /etc/sudoers.d drop-in for ``policy``."""
    tag = "NOPASSWD: ALL" if policy.passwordless else "ALL"
    return f"{MARKER}\n%{policy.group} ALL=(ALL:ALL) {tag}\n"


def parse_sudoers(text: str) -> EscalationPolicy | None:
    """Reconstruct a sudo policy from a drop-in file, or ``None`` if none found."""
    for line in text.splitlines():
        match = _SUDO_RE.match(line.strip())
        if match:
            return EscalationPolicy(
                "sudo", group=match.group("group"),
                passwordless=bool(match.group("nopw")))
    return None


# --- doas (managed block in doas.conf) --------------------------------------

def render_doas_line(policy: EscalationPolicy) -> str:
    parts = ["permit"]
    if policy.passwordless:
        parts.append("nopass")
    elif policy.persist:
        parts.append("persist")
    parts.append(f":{policy.group}")
    return " ".join(parts)


def render_doas_block(policy: EscalationPolicy) -> str:
    return f"{DOAS_BEGIN}\n{render_doas_line(policy)}\n{DOAS_END}\n"


def strip_doas_block(text: str) -> str:
    """Return ``text`` with any GeST-managed block removed (other lines kept)."""
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == DOAS_BEGIN:
            inside = True
            continue
        if stripped == DOAS_END:
            inside = False
            continue
        if not inside:
            out.append(line)
    body = "\n".join(out).rstrip("\n")
    return body + "\n" if body else ""


def has_doas_block(text: str) -> bool:
    return DOAS_BEGIN in text


def apply_doas_block(text: str, policy: EscalationPolicy) -> str:
    """Upsert the GeST block: strip any existing one, then append the new one."""
    base = strip_doas_block(text)
    if base and not base.endswith("\n"):
        base += "\n"
    return base + render_doas_block(policy)


def parse_doas_block(text: str) -> EscalationPolicy | None:
    """Reconstruct the doas policy from the GeST block, or ``None`` if absent."""
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == DOAS_BEGIN:
            inside = True
            continue
        if stripped == DOAS_END:
            break
        if inside and stripped.startswith("permit"):
            tokens = stripped.split()
            group = next((t[1:] for t in tokens if t.startswith(":")), "wheel")
            return EscalationPolicy(
                "doas", group=group,
                passwordless="nopass" in tokens,
                persist="persist" in tokens)
    return None
