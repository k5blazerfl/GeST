"""Read the CPU_FLAGS_X86 / VIDEO_CARDS values GeST currently has set.

Reads only GeST's own fragments (``package.use/50gest-cpuflags`` and
``…/50gest-videocards``), each a single ``*/* VAR: values…`` line parsed with
the shared ``atomfile`` codec.
"""

from __future__ import annotations

from gest.core.hwflags.detect import CPU_FLAGS_VAR, VIDEO_CARDS_VAR
from gest.core.portage import paths
from gest.core.portage.codec import atomfile

CPU_FRAGMENT = "50gest-cpuflags"
VIDEO_FRAGMENT = "50gest-videocards"


def cpu_flags_path() -> str:
    return paths.package_fragment("use", CPU_FRAGMENT)


def video_cards_path() -> str:
    return paths.package_fragment("use", VIDEO_FRAGMENT)


def _read_use_expand(path: str, var: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            rows = atomfile.parse(fh.read())
    except OSError:
        return []
    for row in rows:
        if row.atom == "*/*" and row.tokens[:1] == [f"{var}:"]:
            return row.tokens[1:]
    return []


def current_cpu_flags(path: str | None = None) -> list[str]:
    return _read_use_expand(path or cpu_flags_path(), CPU_FLAGS_VAR)


def current_video_cards(path: str | None = None) -> list[str]:
    return _read_use_expand(path or video_cards_path(), VIDEO_CARDS_VAR)
