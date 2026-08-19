"""Unprivileged hardware detection for CPU_FLAGS_X86 and VIDEO_CARDS.

Both take an injectable ``runner`` (``argv -> (returncode, output)``) so they
are testable without the real tools, mirroring ``core/software/preview.py``.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable

Runner = Callable[[list[str]], tuple[int, str]]

CPU_FLAGS_VAR = "CPU_FLAGS_X86"
VIDEO_CARDS_VAR = "VIDEO_CARDS"

# GPU vendor substrings (in an lspci display line) → recommended VIDEO_CARDS.
_VIDEO_MAP: list[tuple[tuple[str, ...], list[str]]] = [
    (("nvidia",), ["nvidia"]),
    (("amd", "ati ", "radeon", "advanced micro devices"), ["amdgpu", "radeonsi"]),
    (("intel",), ["intel"]),
]


def _default_runner(argv: list[str]) -> tuple[int, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def detect_cpu_flags(runner: Runner = _default_runner) -> list[str]:
    """The CPU_FLAGS_X86 tokens from ``cpuid2cpuflags`` (``[]`` if unavailable).

    ``cpuid2cpuflags`` prints a single line ``CPU_FLAGS_X86: mmx sse ...``.
    """
    try:
        rc, out = runner(["cpuid2cpuflags"])
    except FileNotFoundError:
        return []
    if rc != 0:
        return []
    for line in out.splitlines():
        if ":" in line:
            _key, _, rest = line.partition(":")
            return rest.split()
    return out.split()


_GPU_CLASS = ("vga", "3d controller", "display controller")

# NVIDIA GPU-architecture codename prefixes that support the OPEN kernel modules:
# Turing (TU), Ampere (GA), Ada (AD), Blackwell (GB). Pre-Turing (GP/GM/GK…) do not.
_NVIDIA_OPEN_RE = re.compile(r"\b(?:TU|GA|AD|GB)\d{2,3}\b")


def parse_video_cards(lspci_text: str) -> list[str]:
    """Recommended VIDEO_CARDS tokens from raw ``lspci`` output (pure)."""
    cards: list[str] = []
    for line in lspci_text.splitlines():
        low = line.lower()
        if not any(k in low for k in _GPU_CLASS):
            continue
        for needles, tokens in _VIDEO_MAP:
            if any(n in low for n in needles):
                for tok in tokens:
                    if tok not in cards:
                        cards.append(tok)
    return cards


def nvidia_open_recommended(lspci_text: str) -> bool:
    """True if an NVIDIA GPU line names a Turing-or-newer codename, i.e. the open
    kernel modules are supported (and NVIDIA-recommended). Conservative: a card whose
    codename ``lspci`` doesn't spell out returns ``False`` (use the closed module)."""
    for line in lspci_text.splitlines():
        low = line.lower()
        if ("nvidia" in low and any(k in low for k in _GPU_CLASS)
                and _NVIDIA_OPEN_RE.search(line)):
            return True
    return False


def detect_video_cards(runner: Runner = _default_runner) -> list[str]:
    """Recommended VIDEO_CARDS tokens from ``lspci`` (``[]`` if none/unavailable)."""
    try:
        rc, out = runner(["lspci"])
    except FileNotFoundError:
        return []
    if rc != 0:
        return []
    return parse_video_cards(out)
