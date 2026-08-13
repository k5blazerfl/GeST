"""The escalation policy and the well-known paths/markers the module manages."""

from __future__ import annotations

from dataclasses import dataclass

SUDOERS_DROPIN = "/etc/sudoers.d/10-gest-wheel"
DOAS_CONF = "/etc/doas.conf"

# Delimiters for the block GeST owns inside /etc/doas.conf (which has no drop-in
# directory). Everything outside these markers is left untouched.
DOAS_BEGIN = "# >>> gest managed (do not edit this block) >>>"
DOAS_END = "# <<< gest managed <<<"


@dataclass(slots=True, frozen=True)
class EscalationPolicy:
    """A wheel-style escalation rule for one tool.

    ``passwordless`` maps to sudo ``NOPASSWD:`` / doas ``nopass``. ``persist`` is
    doas-only (cache the auth for a few minutes, like sudo's timestamp); it is
    ignored when ``passwordless`` is set and for sudo.
    """

    tool: str                       # "sudo" | "doas"
    group: str = "wheel"
    passwordless: bool = False
    persist: bool = True
