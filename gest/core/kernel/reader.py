"""Read kernel-source state (unprivileged) for the build screen.

Which /usr/src/linux-* trees exist, which one /usr/src/linux points at, whether
it has a .config yet, whether genkernel/dracut are installed, and the CPU count
(the default -j). Parsing is pure over its inputs so it's CI-testable; the module
functions wire it to the live host.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

SRC_ROOT = "/usr/src"
CURRENT_LINK = "/usr/src/linux"


@dataclass(slots=True)
class KernelBuildInfo:
    current: str = ""                 # basename of /usr/src/linux target
    source_dir: str = ""              # absolute source dir, or ""
    has_config: bool = False          # .config present in the source dir
    sources: list[str] = field(default_factory=list)   # available linux-* trees
    genkernel: bool = False
    dracut: bool = False
    cpus: int = 1


def parse_sources(names: list[str]) -> list[str]:
    """Kernel-source tree names (linux-*) from /usr/src entries, newest first."""
    return sorted((n for n in names if n.startswith("linux-")), reverse=True)


def kernel_sources(src_root: str = SRC_ROOT) -> list[str]:
    try:
        return parse_sources(os.listdir(src_root))
    except OSError:
        return []


def current_source(link: str = CURRENT_LINK) -> str:
    try:
        return os.path.basename(os.readlink(link))
    except OSError:
        return ""


def has_config(source_dir: str) -> bool:
    return bool(source_dir) and os.path.exists(os.path.join(source_dir, ".config"))


def cpu_count() -> int:
    return os.cpu_count() or 1


def build_info() -> KernelBuildInfo:
    current = current_source()
    source_dir = os.path.join(SRC_ROOT, current) if current else ""
    return KernelBuildInfo(
        current=current,
        source_dir=source_dir,
        has_config=has_config(source_dir),
        sources=kernel_sources(),
        genkernel=bool(shutil.which("genkernel")),
        dracut=bool(shutil.which("dracut")),
        cpus=cpu_count(),
    )
