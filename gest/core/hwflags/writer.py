"""Build the :class:`ConfigWrite`\\ s for the CPU_FLAGS_X86 / VIDEO_CARDS fragments.

Each fragment is one ``*/* VAR: values…`` line that GeST fully owns; an empty
value list renders to ``""`` so the backend deletes the fragment. Applied via
the Portage ``WriteConfig`` RPC.
"""

from __future__ import annotations

from gest.core.hwflags.detect import CPU_FLAGS_VAR, VIDEO_CARDS_VAR
from gest.core.hwflags.reader import cpu_flags_path, video_cards_path
from gest.core.portage.write import ConfigWrite


def use_expand_line(var: str, values: list[str]) -> str:
    """The ``*/* VAR: a b c`` line for a USE_EXPAND var (``""`` if no values)."""
    toks = [v for v in values if v]
    return f"*/* {var}: {' '.join(toks)}" if toks else ""


def _write(path: str, var: str, values: list[str]) -> ConfigWrite:
    line = use_expand_line(var, values)
    return ConfigWrite(path, line + "\n" if line else "")


def write_cpu_flags(flags: list[str], *, path: str | None = None) -> ConfigWrite:
    """A :class:`ConfigWrite` for the 50gest-cpuflags fragment."""
    return _write(path or cpu_flags_path(), CPU_FLAGS_VAR, flags)


def write_video_cards(cards: list[str], *, path: str | None = None) -> ConfigWrite:
    """A :class:`ConfigWrite` for the 50gest-videocards fragment."""
    return _write(path or video_cards_path(), VIDEO_CARDS_VAR, cards)
