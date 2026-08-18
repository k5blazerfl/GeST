"""Extract an icon from a Windows ``.exe`` and place it in the XDG icon theme.

Windows executables carry their icons as PE resources; icoutils' ``wrestool``
pulls them out. This module builds the extraction argv and the theme install
path (both pure/testable); the caller runs ``wrestool`` and drops the file.

The icon *name* a ``.desktop`` should reference is just ``<icon_id>`` (no path,
no extension) once the file lives under ``…/icons/hicolor/<size>/apps/``.
"""

from __future__ import annotations

from pathlib import Path

ICON_THEME_DIR = "~/.local/share/icons/hicolor"


def extract_argv(exe_path: str, out_path: str, *, index: int = 1) -> list[str]:
    """``wrestool -x -t 14 -n <index> -o <out> <exe>`` — extract group-icon
    resource ``index`` (type 14 = RT_GROUP_ICON) from ``exe`` to ``out``."""
    return ["wrestool", "-x", "-t", "14", "-n", str(index), "-o", out_path, exe_path]


def convert_argv(ico_path: str, out_path: str, *, width: str = "48") -> list[str]:
    """``icotool -x -w <width> -o <out> <ico>`` — extract the ``width``-px image
    from an ``.ico`` (as produced by :func:`extract_argv`) to a PNG (icoutils)."""
    return ["icotool", "-x", "-w", width, "-o", out_path, ico_path]


def icon_install_path(icon_id: str, *, size: str = "48x48",
                      theme_dir: str = ICON_THEME_DIR, ext: str = "png") -> Path:
    """Where an extracted icon named ``icon_id`` belongs in the hicolor theme."""
    return Path(theme_dir).expanduser() / size / "apps" / f"{icon_id}.{ext}"


def scalable_install_path(icon_id: str, *, theme_dir: str = ICON_THEME_DIR) -> Path:
    """The scalable (SVG) slot, for a vector icon."""
    return Path(theme_dir).expanduser() / "scalable" / "apps" / f"{icon_id}.svg"
