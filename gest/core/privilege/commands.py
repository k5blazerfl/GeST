"""Pure argv builders for the sudo/doas config checkers. No I/O; CI-testable."""

from __future__ import annotations


def visudo_check_argv(path: str, *, visudo: str = "visudo") -> list[str]:
    """Syntax-check a sudoers file without installing it (`visudo -c -f`)."""
    return [visudo, "-c", "-f", path]


def doas_check_argv(path: str, *, doas: str = "doas") -> list[str]:
    """Parse-check a doas.conf without applying it (`doas -C`)."""
    return [doas, "-C", path]
