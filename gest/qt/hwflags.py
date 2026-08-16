"""CPU & Video flags module logic: pure format/parse helpers + apply via the
shared Portage ``WriteConfig`` backend (the same polkit-gated RPC make.conf uses).
"""

from __future__ import annotations

from gest.core.hwflags.writer import write_cpu_flags, write_video_cards
from gest.qt.portageconf import apply_writes


def format_flags(flags: list[str]) -> str:
    """Space-joined flags for an editable field."""
    return " ".join(flags)


def parse_flags(text: str) -> list[str]:
    """Whitespace-separated tokens, order preserved, duplicates dropped."""
    out: list[str] = []
    for token in text.split():
        if token not in out:
            out.append(token)
    return out


def apply_cpu_flags(flags: list[str]) -> tuple[bool, str]:
    """Write the CPU_FLAGS_X86 fragment (an empty list clears it)."""
    return apply_writes([write_cpu_flags(flags)])


def apply_video_cards(cards: list[str]) -> tuple[bool, str]:
    """Write the VIDEO_CARDS fragment (an empty list clears it)."""
    return apply_writes([write_video_cards(cards)])
