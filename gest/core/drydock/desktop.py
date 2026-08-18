"""Drydock ↔ Customs: synthesize launchers, and harvest wine's own `.desktop`s.

Two paths (both resolved design decisions):

1. **Synthesize** — build a Customs ``.desktop`` for a registered program whose
   ``Exec`` runs ``drydock-run <barrel> <program>`` (so the launch goes through
   Drydock's pipeline), with the right icon name, category, and
   ``StartupWMClass`` for taskbar identity.
2. **Harvest** — scan the ``.desktop`` files wine's winemenubuilder auto-writes
   (installers create Start-menu shortcuts) and turn them into Drydock programs,
   so an installed app is adopted rather than re-specified by hand.

Pure: rendering and the wine-Exec exe extraction are string work; only the
filesystem scan touches disk.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path, PureWindowsPath

from gest.core.customs import mime
from gest.core.customs.desktop import DesktopEntry, build_exec
from gest.core.customs.desktop import entry_path as _customs_entry_path
from gest.core.drydock.barrels import slug
from gest.core.drydock.model import Barrel, Program

DRYDOCK_RUN = "drydock-run"
# wine's winemenubuilder writes generated launchers here.
WINE_APPS_DIR = "~/.local/share/applications/wine"


def open_argv(barrel_id: str, program_id: str) -> list[str]:
    return [DRYDOCK_RUN, barrel_id, program_id]


def desktop_id(barrel_id: str, program_id: str) -> str:
    return f"drydock-{barrel_id}-{slug(program_id)}"


def _exe_stem(exe: str) -> str:
    """Basename without extension, tolerating Windows ('C:\\a\\b.exe') and unix
    paths — used as a default WM_CLASS."""
    tail = exe.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return PureWindowsPath(tail).stem or tail


def default_wm_class(program: Program) -> str:
    """The WM_CLASS a program presents: its explicit ``wm_class`` else the exe
    stem. This is both the launcher's ``StartupWMClass`` and the key the Customs
    identity map registers, so the taskbar can match the window to the launcher."""
    return program.wm_class or _exe_stem(program.exe)


_WIN_DRIVE = re.compile(r"^([A-Za-z]):/(.*)$")


def local_exe_path(barrel: Barrel, program: Program) -> str:
    """Resolve a program's exe to a real host path (for icon extraction). A
    Windows path like ``C:\\office\\excel.exe`` maps to ``<prefix>/drive_c/…``; a
    unix path (e.g. a harvested wine Exec) is used as-is. Empty if unresolved."""
    exe = program.exe
    if not exe:
        return ""
    unixish = exe.replace("\\", "/")
    match = _WIN_DRIVE.match(unixish)
    if match and barrel.prefix:
        drive, rest = match.group(1).lower(), match.group(2)
        return str(Path(barrel.prefix).expanduser() / f"drive_{drive}" / rest)
    return exe


def desktop_entry(barrel: Barrel, program: Program) -> DesktopEntry:
    categories = ["Game"] if program.category == "Game" else ["Utility"]
    return DesktopEntry(
        name=program.name,
        exec=build_exec(open_argv(barrel.id, program.id)),
        icon=desktop_id(barrel.id, program.id),
        comment=f"{program.name} — Drydock: {barrel.name}",
        categories=categories,
        mime_types=list(mime.DRYDOCK_TYPES),
        startup_wm_class=default_wm_class(program),
        extra={"X-GeST-Origin": "drydock", "X-Drydock-Barrel": barrel.id,
               "X-Drydock-Program": program.id},
    )


# ---- harvesting wine's generated launchers -----------------------------
def _extract_exe(exec_line: str) -> str:
    """Best-effort: pull the Windows executable out of a wine-generated Exec."""
    try:
        tokens = shlex.split(exec_line)
    except ValueError:
        tokens = exec_line.split()
    tokens = [t for t in tokens if not t.startswith("%")]  # drop field codes
    for token in reversed(tokens):
        if token.lower().endswith((".exe", ".msi", ".lnk", ".bat")):
            return token
    for i, token in enumerate(tokens):
        if token in ("wine", "wine64") and i + 1 < len(tokens):
            nxt = tokens[i + 1]
            if nxt not in ("start", "/unix"):
                return nxt
    return tokens[-1] if tokens else ""


def harvest_dir(wine_apps_dir: str = WINE_APPS_DIR) -> list[DesktopEntry]:
    """Parse every ``.desktop`` wine generated under ``wine_apps_dir``."""
    directory = Path(wine_apps_dir).expanduser()
    if not directory.is_dir():
        return []
    entries = []
    for path in sorted(directory.rglob("*.desktop")):
        try:
            entries.append(DesktopEntry.parse(path.read_text(encoding="utf-8")))
        except OSError:
            continue
    return entries


def program_from_harvested(entry: DesktopEntry, program_id: str) -> Program:
    """Turn a harvested wine ``.desktop`` into a Drydock program."""
    return Program(
        id=program_id,
        name=entry.name or program_id,
        exe=_extract_exe(entry.exec),
        category="Game" if "Game" in entry.categories else "Application",
        wm_class=entry.startup_wm_class,
    )


def entry_path(barrel_id: str, program_id: str, applications_dir: str) -> Path:
    return _customs_entry_path(desktop_id(barrel_id, program_id), applications_dir)
