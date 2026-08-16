"""Consume the shared Helm appearance so the Control Center matches HeDE.

A faithful Python port of the shell's ``helm::applyAppearance()`` /
``buildPalette()`` (``hede/src/appearance/palette.cpp``): read the same
``$XDG_CONFIG_HOME/hede/hede.conf`` ``[appearance]`` block (``dark`` + ``accent``,
written by ``helm-theme``), and apply the matching ``QPalette`` + Fusion style to
the running ``QApplication`` — exactly what ``hede/src/menu/main.cpp`` does. A
no-op when nothing is themed, so the Control Center keeps its native look until
the user picks a theme, just like the shell and the Start menu.

Icons (``QIcon.fromTheme`` on the descriptors) are layer B, handled separately.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication


def fixed_font() -> QFont:
    """The platform fixed-width font — for terminal-like views (emerge output,
    plan previews, the sysctl dump). Typography, not colour, so it never fights
    the shared Helm palette."""
    return QFontDatabase.systemFont(QFontDatabase.FixedFont)


def hede_conf_path() -> str:
    """The shared HeDE config file — same path the C++ shell reads/writes."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "hede", "hede.conf")


def contrast_text(bg: QColor) -> QColor:
    """Readable text colour (black/white) for a background — ports contrastText."""
    lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
    return QColor(Qt.black) if lum > 140 else QColor(Qt.white)


def build_palette(dark: bool, accent: QColor) -> QPalette:
    """A shell palette: dark or light base, ``accent`` as the Highlight — ports
    ``helm::buildPalette`` colour-for-colour so the two frontends match."""
    p = QPalette()  # default = light
    if dark:
        window = QColor(0x2B, 0x2B, 0x2B)
        base = QColor(0x1E, 0x1E, 0x1E)
        alt = QColor(0x24, 0x24, 0x24)
        text = QColor(0xE6, 0xE6, 0xE6)
        button = QColor(0x32, 0x32, 0x32)
        disabled = QColor(0x7F, 0x7F, 0x7F)
        p.setColor(QPalette.Window, window)
        p.setColor(QPalette.WindowText, text)
        p.setColor(QPalette.Base, base)
        p.setColor(QPalette.AlternateBase, alt)
        p.setColor(QPalette.Text, text)
        p.setColor(QPalette.Button, button)
        p.setColor(QPalette.ButtonText, text)
        p.setColor(QPalette.ToolTipBase, window)
        p.setColor(QPalette.ToolTipText, text)
        p.setColor(QPalette.PlaceholderText, disabled)
        p.setColor(QPalette.Disabled, QPalette.Text, disabled)
        p.setColor(QPalette.Disabled, QPalette.WindowText, disabled)
        p.setColor(QPalette.Disabled, QPalette.ButtonText, disabled)
    if accent.isValid():
        p.setColor(QPalette.Highlight, accent)
        p.setColor(QPalette.HighlightedText, contrast_text(accent))
    return p


def read_appearance(path: str | None = None) -> tuple[bool, QColor]:
    """(dark, accent) from hede.conf ``[appearance]``; accent invalid if unset."""
    settings = QSettings(path or hede_conf_path(), QSettings.IniFormat)
    dark = str(settings.value("appearance/dark", "")).strip().lower() == "true"
    accent = QColor(str(settings.value("appearance/accent", "")))
    return dark, accent


def apply_appearance(app: QApplication | None = None, *, path: str | None = None) -> bool:
    """Apply the Helm palette + Fusion to ``app``. Returns False (and changes
    nothing) when nothing is themed — the native-look no-op the shell uses."""
    dark, accent = read_appearance(path)
    if not dark and not accent.isValid():
        return False  # nothing themed → keep the native look
    app = app or QApplication.instance()
    if isinstance(app, QApplication):
        app.setStyle("Fusion")  # honours a custom palette
    QGuiApplication.setPalette(build_palette(dark, accent))
    return True
