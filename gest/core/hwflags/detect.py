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

# Pre-GCN AMD/ATI chip families (TeraScale and older) that the modern ``amdgpu``
# kernel driver does NOT support — they need the ``radeon`` driver + its mesa
# gallium backends instead. Matched as codename/family substrings in the lspci
# line. GCN 1.0+ ("Southern Islands"/Bonaire and newer, ~2012+) uses amdgpu and is
# the default, so only the legacy families are enumerated here.
_AMD_LEGACY_RADEON = (
    # TeraScale 2/3 (HD 5000/6000, Evergreen/Northern Islands) + Fusion APUs
    "cedar", "redwood", "juniper", "cypress", "hemlock",
    "caicos", "turks", "barts", "cayman", "antilles",
    "wrestler", "ontario", "zacate", "llano", "sumo", "trinity", "richland",
    # TeraScale 1 (HD 2000/3000/4000, R600/R700)
    "r600", "rv6", "rv7", "rs780", "rs880",
)
_AMD_LEGACY_TOKENS = ["radeon", "r600"]      # mesa gallium backends for TeraScale


def _default_runner(argv: list[str]) -> tuple[int, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def detect_cpu_flags(runner: Runner = _default_runner) -> list[str]:
    """The CPU_FLAGS_X86 tokens from ``cpuid2cpuflags`` (``[]`` if unavailable).

    ``cpuid2cpuflags`` prints a single line ``CPU_FLAGS_X86: mmx sse ...``.
    """
    try:
        rc, out = runner(["cpuid2cpuflags"])
    except OSError:                      # missing binary (ENOENT) OR an exec/IO error (EIO)
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

# NVIDIA architecture codename (as it appears in ``lspci``, e.g. "GK107",
# "GF119", "AD103") → proprietary driver branch. NVIDIA splits the closed driver
# by GPU generation, and Gentoo ships each as a separate SLOT of
# ``x11-drivers/nvidia-drivers``:
#   * "current"    — the maintained slot (Maxwell GM / Pascal GP / Volta GV closed;
#                    Turing TU / Ampere GA / Ada AD / Blackwell GB, open-capable)
#   * "legacy-470" — Kepler (GK): SLOT 0/470, masked upstream (needs package.unmask)
#   * "legacy-390" — Fermi  (GF): SLOT 0/390, masked upstream (needs package.unmask)
#   * "nouveau"    — Tesla (G8x/G9x/GT2xx) and older: no supported in-tree
#                    proprietary driver (the 340 branch is gone) → use nouveau.
# Order matters: the first matching pattern wins.
_NVIDIA_ARCH: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bAD\d{3}\b"), "current"),      # Ada Lovelace   (RTX 40)
    (re.compile(r"\bGB\d{3}\b"), "current"),      # Blackwell      (RTX 50)
    (re.compile(r"\bGA\d{3}\b"), "current"),      # Ampere         (RTX 30)
    (re.compile(r"\bTU\d{3}\b"), "current"),      # Turing         (RTX 20 / GTX 16)
    (re.compile(r"\bGV\d{3}\b"), "current"),      # Volta          (TITAN V)
    (re.compile(r"\bGP\d{3}\b"), "current"),      # Pascal         (GTX 10)
    (re.compile(r"\bGM\d{3}\b"), "current"),      # Maxwell        (GTX 9xx)
    (re.compile(r"\bGK\d{3}\b"), "legacy-470"),   # Kepler         (GTX 6xx/7xx)
    (re.compile(r"\bGF\d{3}\b"), "legacy-390"),   # Fermi          (GTX 4xx/5xx)
    (re.compile(r"\b(?:G[89]\d|GT2\d{2})\b"), "nouveau"),  # Tesla (8/9/2xx/3xx)
)

# Driver branch → the nvidia-drivers SLOT atom suffix. "current" is the default
# (unmasked) slot and needs no explicit slot; the legacy slots are masked upstream.
NVIDIA_SLOTS: dict[str, str] = {"legacy-470": "0/470", "legacy-390": "0/390"}


def _nvidia_gpu_lines(lspci_text: str):
    """Yield each lspci line that names an NVIDIA GPU (VGA/3D/display class)."""
    for line in lspci_text.splitlines():
        low = line.lower()
        if "nvidia" in low and any(k in low for k in _GPU_CLASS):
            yield line


def nvidia_driver_branch(lspci_text: str) -> str:
    """The proprietary-driver branch for the first NVIDIA GPU in ``lspci`` output.

    Returns ``""`` when there is no NVIDIA GPU; otherwise one of ``"current"``,
    ``"legacy-470"`` (Kepler), ``"legacy-390"`` (Fermi), or ``"nouveau"`` (Tesla
    and older, which have no supported in-tree proprietary driver). An NVIDIA card
    whose codename ``lspci`` doesn't spell out falls back to ``"current"`` — the
    common case is a newer card; genuinely old unrecognized cards can be switched
    to nouveau in the installer.
    """
    saw_nvidia = False
    for line in _nvidia_gpu_lines(lspci_text):
        saw_nvidia = True
        for rx, branch in _NVIDIA_ARCH:
            if rx.search(line):
                return branch
    return "current" if saw_nvidia else ""


def amd_legacy_radeon(lspci_text: str) -> bool:
    """True if an AMD/ATI GPU line names a pre-GCN (TeraScale-or-older) family that
    needs the ``radeon`` driver rather than the modern ``amdgpu``. Conservative:
    anything not recognized as legacy is treated as amdgpu-capable."""
    for line in lspci_text.splitlines():
        low = line.lower()
        if not any(k in low for k in _GPU_CLASS):
            continue
        if not any(n in low for n in ("amd", "ati ", "radeon", "advanced micro devices")):
            continue
        if any(fam in low for fam in _AMD_LEGACY_RADEON):
            return True
    return False


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
    except OSError:                      # missing binary (ENOENT) OR an exec/IO error (EIO)
        return []
    if rc != 0:
        return []
    return parse_video_cards(out)
