"""Consume the shared Helm appearance so the Control Center matches HeDE.

A faithful Python port of the shell's ``helm::applyAppearance()`` /
``buildPalette()`` / ``styleSheet()`` (``hede/src/appearance/palette.cpp`` +
``style.cpp``): read the same ``$XDG_CONFIG_HOME/hede/hede.conf`` block (the
``[appearance]`` mode/accent AND the active ``[world] id``) the shell reads, then
apply the matching **Fusion style + QPalette + the Helm glass QSS** to the running
``QApplication`` — exactly what the C++ apps do. Previously this applied only a
palette and only when a legacy ``appearance/dark``/``accent`` was set, so a
world-themed desktop left the Control Center unstyled; now it wears the same
world-tinted glass chrome (``#HelmAppWindow`` etc.) as SeFE and the shell.

Icons (``QIcon.fromTheme`` on the descriptors) are layer B, handled separately.
"""

from __future__ import annotations

import os
import re

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

#: The object name the Helm glass QSS scopes app chrome to (``#HelmAppWindow`` in
#: style.cpp). A top-level window must carry it to receive the world-glass menu/
#: tool/status-bar styling — SeFE sets it; the Control Center now does too.
HELM_APP_WINDOW = "HelmAppWindow"


def fixed_font() -> QFont:
    """The platform fixed-width font — for terminal-like views (emerge output,
    plan previews, the sysctl dump). Typography, not colour, so it never fights
    the shared Helm palette."""
    return QFontDatabase.systemFont(QFontDatabase.FixedFont)


def hede_conf_path() -> str:
    """The shared HeDE config file — same path the C++ shell reads/writes."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "hede", "hede.conf")


# --- accent / glass helpers (port of style.cpp) -----------------------------

def harbor_accent() -> QColor:
    """The default world accent when the user hasn't chosen one (worlds.harbor)."""
    return QColor("#3aa6c4")


def bar_glyph() -> QColor:
    """Light bar glyph colour on the world-navy glass (icons.cpp:barGlyphColor)."""
    return QColor("#eaf1f3")


def bar_tint(accent: QColor) -> QColor:
    """The world-tinted deep glass for the bars — the accent's hue at low value,
    high saturation (ports ``helm::barTint``). Achromatic accent → Harbor hue."""
    a = accent if accent.isValid() else harbor_accent()
    h = a.hsvHue()
    if h < 0:
        h = harbor_accent().hsvHue()
    return QColor.fromHsv(h, 190, 46)


def _rgba(c: QColor, alpha: float) -> str:
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha:.2f})"


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


def style_sheet(accent: QColor) -> str:
    """The HeDE shell QSS (the Harbor glass look), tinted by ``accent`` — a faithful
    port of ``helm::styleSheet``. ``dark`` is deliberately not a parameter: body
    light/dark is the palette's job; the glass chrome is always deep glass. Scoped so
    ``#HelmAppWindow`` chrome/rows pick up the world tint without touching a plain app."""
    a = accent if accent.isValid() else harbor_accent()
    accent_fill = _rgba(a, 0.34)          # selection fill (34%)
    accent_edge = _rgba(a, 0.55)          # selection border (55%)
    glass = bar_tint(a)                   # world-tinted deep glass
    bar_glass = _rgba(glass, 0.82)
    acrylic_glass = _rgba(glass, 0.92)
    field_glass = bar_tint(a).darker(118).name()
    glyph = bar_glyph().name()
    aname = a.name()

    return "\n".join((
        # Shared token look — every shell surface.
        '* { font-family: "Segoe UI", "Inter", system-ui, sans-serif; }',
        "QAbstractItemView { outline: none; }",
        "QAbstractItemView::item { border-radius: 5px; padding: 2px 6px; }",
        f"QAbstractItemView::item:selected {{ background: {accent_fill}; color: palette(text); }}",
        "QLineEdit { border: 1px solid rgba(127,127,127,0.35); border-radius: 4px;"
        " padding: 4px 8px; }",
        f"QLineEdit:focus {{ border: 1px solid {accent_edge}; }}",
        # The glass bar (#HelmBar).
        f"#HelmBar {{ background: {bar_glass}; border: none;"
        " border-top: 1px solid rgba(255,255,255,0.28); }",
        f"#HelmBar QLabel {{ color: {glyph}; background: transparent; }}",
        f"#HelmBar QToolButton, #HelmBar QPushButton {{ color: {glyph};"
        " background: transparent; border: none; border-radius: 5px; padding: 2px 8px; }",
        "#HelmBar QToolButton:hover, #HelmBar QPushButton:hover"
        " { background: rgba(255,255,255,0.14); }",
        "#HelmBar QToolButton:pressed, #HelmBar QPushButton:pressed,"
        " #HelmBar QToolButton:checked, #HelmBar QPushButton:checked"
        f" {{ background: {accent_fill}; }}",
        "#HelmBar #HelmStart { font-size: 15px; font-weight: 600; padding: 0 10px; }",
        # The acrylic pullout (#HelmPullout).
        f"#HelmPullout {{ background: {acrylic_glass};"
        " border: 1px solid rgba(255,255,255,0.22); border-bottom: none;"
        " border-top-left-radius: 7px; border-top-right-radius: 7px;"
        " border-bottom-left-radius: 0; border-bottom-right-radius: 0; }",
        f"#HelmPullout QLabel {{ color: {glyph}; background: transparent; }}",
        f"#HelmPullout QListWidget, #HelmPullout QListView {{ background: transparent;"
        f" border: none; color: {glyph}; }}",
        f"#HelmPullout QListWidget::item {{ color: {glyph}; padding: 4px 8px;"
        " border-radius: 5px; }",
        f"#HelmPullout QListWidget::item:selected {{ background: {accent_fill}; color: {glyph}; }}",
        f"#HelmPullout QLineEdit {{ background: rgba(255,255,255,0.10); color: {glyph};"
        " border: 1px solid rgba(255,255,255,0.18); border-radius: 5px; padding: 6px 10px; }",
        f"#HelmPullout QLineEdit:focus {{ border: 1px solid {accent_edge}; }}",
        f"#HelmPullout QToolButton, #HelmPullout QPushButton {{ color: {glyph};"
        " background: transparent; border: none; border-radius: 5px; padding: 6px 8px; }",
        "#HelmPullout QToolButton:hover, #HelmPullout QPushButton:hover"
        " { background: rgba(255,255,255,0.12); }",
        "#HelmMenuRail { border-left: 1px solid rgba(255,255,255,0.14); }",
        f"#HelmClassicCaption {{ background: {accent_fill}; border-top-left-radius: 7px; }}",
        f"#HelmClassicCaption QLabel {{ color: {glyph}; background: transparent; }}",
        # Acrylic toast cards (#HelmToast).
        f"#HelmToast {{ background: {acrylic_glass};"
        f" border: 1px solid rgba(255,255,255,0.22); border-left: 3px solid {aname};"
        " border-radius: 7px; }",
        f"#HelmToast QLabel {{ color: {glyph}; background: transparent; }}",
        f"#HelmToast #HelmToastTitle {{ color: {glyph}; font-weight: 700; }}",
        # HeDE application chrome (#HelmAppWindow) — the Control Center + SeFE.
        f"#HelmAppWindow QMenuBar {{ background: {bar_glass}; color: {glyph}; border: none; }}",
        "#HelmAppWindow QMenuBar::item { background: transparent; padding: 4px 10px;"
        " border-radius: 5px; }",
        "#HelmAppWindow QMenuBar::item:selected, #HelmAppWindow QMenuBar::item:pressed"
        f" {{ background: {accent_fill}; color: {glyph}; }}",
        f"#HelmAppWindow QToolBar {{ background: {bar_glass}; border: none; spacing: 2px;"
        " padding: 3px 4px; }",
        f"#HelmAppWindow QToolBar QToolButton {{ color: {glyph}; background: transparent;"
        " border: none; border-radius: 5px; padding: 3px 6px; }",
        "#HelmAppWindow QToolBar QToolButton:hover { background: rgba(255,255,255,0.14); }",
        "#HelmAppWindow QToolBar QToolButton:pressed,"
        f" #HelmAppWindow QToolBar QToolButton:checked {{ background: {accent_fill}; }}",
        f"#HelmAppWindow QToolBar QLabel {{ color: {glyph}; background: transparent; }}",
        f"#HelmAppWindow QStatusBar {{ background: {bar_glass}; color: {glyph}; }}",
        f"#HelmAppWindow QStatusBar QLabel {{ color: {glyph}; }}",
        "#HelmAppWindow QStatusBar::item { border: none; }",
        # The address field + Places pane (SeFE; harmless elsewhere).
        f"#HelmAddressBar {{ background: {field_glass};"
        " border: 1px solid rgba(255,255,255,0.14); border-radius: 5px; }",
        "#HelmAddressBar QStackedWidget, #HelmAddressBar QWidget { background: transparent; }",
        f"#HelmAddressBar QToolButton {{ color: {glyph}; background: transparent; border: none;"
        " border-radius: 4px; padding: 2px 6px; }",
        "#HelmAddressBar QToolButton:hover { background: rgba(255,255,255,0.12); }",
        f"#HelmAddressBar QLabel {{ color: {glyph}; background: transparent; }}",
        f"#HelmAddressBar QLineEdit {{ background: transparent; color: {glyph}; border: none; }}",
        "#HelmAddressBar QLineEdit:focus { border: none; }",
        f"#HelmAppPlaces {{ background: {acrylic_glass}; border: none; color: {glyph}; }}",
        f"#HelmAppPlaces::item {{ color: {glyph}; border-radius: 5px; padding: 5px 8px; }}",
        "#HelmAppPlaces::item:hover { background: rgba(255,255,255,0.10); }",
        f"#HelmAppPlaces::item:selected {{ background: {accent_fill}; color: {glyph}; }}",
        # Scene mode (SeFE frameless chrome) — bars go transparent so the scene shows.
        '#HelmAppWindow[helmScene="true"] QMenuBar,'
        ' #HelmAppWindow[helmScene="true"] QToolBar,'
        ' #HelmAppWindow[helmScene="true"] QStatusBar,'
        " #HelmHeader { background: transparent; }",
        "#HelmAppBody { background: palette(window); }",
        "#HelmAppBodyInset { background: transparent; }",
        "#HelmTitleBar { background: transparent; }",
        f"#HelmTitleText {{ color: {glyph}; font-weight: 600; padding-left: 2px; }}",
        f"#HelmTitleBar QToolButton {{ color: {glyph}; background: transparent; border: none;"
        " border-radius: 4px; font-size: 14px; }",
        "#HelmTitleBar QToolButton:hover { background: rgba(255,255,255,0.16); }",
        f"#HelmWinClose {{ color: {glyph}; background: transparent; border: none;"
        " border-radius: 4px; font-size: 14px; }",
        "#HelmWinClose:hover { background: rgba(232,64,64,0.90); color: white; }",
        # Archive affordances (Seahorse).
        f"#HelmCrumbArchive {{ color: {glyph}; background: {accent_fill};"
        f" border: 1px solid {accent_edge};"
        " border-radius: 5px; padding: 1px 7px; font-weight: 600; }",
        f"#HelmCrumbArchive:hover {{ background: {accent_edge}; }}",
        f"#HelmReadOnlyPill {{ color: {glyph}; background: {accent_fill};"
        f" border: 1px solid {accent_edge};"
        " border-radius: 8px; padding: 1px 9px; margin-right: 4px; }",
    )) + "\n"


# --- reading the shared config ----------------------------------------------

def _world_dirs() -> list[str]:
    """Where installed world themes live (``share/hede/worlds``), XDG-first."""
    dirs = []
    xdg = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    for d in xdg.split(":"):
        if d:
            dirs.append(os.path.join(d, "hede", "worlds"))
    if "/usr/share/hede/worlds" not in dirs:
        dirs.append("/usr/share/hede/worlds")
    return dirs


_ACCENT_RE = re.compile(r"""\s*accent\s*:\s*['"]?(#[0-9A-Fa-f]{3,8})""")


def world_accent(world_id: str, *, dirs: list[str] | None = None) -> QColor:
    """The active world's accent from ``worlds/<id>/theme.yaml`` (a one-line
    ``accent: '#…'`` — read directly, no YAML dep). Invalid if not found."""
    for base in (dirs if dirs is not None else _world_dirs()):
        try:
            with open(os.path.join(base, world_id, "theme.yaml"), encoding="utf-8") as fh:
                for line in fh:
                    m = _ACCENT_RE.match(line)
                    if m:
                        return QColor(m.group(1))
        except OSError:
            continue
    return QColor()


def _resolve_dark(settings: QSettings) -> bool:
    """Light/dark for the palette from ``[appearance] mode`` (dark/light), falling
    back to the legacy ``dark`` bool — mirrors ``palette.cpp:configDark`` (the
    follow-the-sun ``auto`` mode is not resolved here; it falls back to legacy)."""
    mode = str(settings.value("appearance/mode", "")).strip().lower()
    if mode == "dark":
        return True
    if mode == "light":
        return False
    return str(settings.value("appearance/dark", "")).strip().lower() == "true"


def read_appearance(path: str | None = None) -> tuple[bool, QColor]:
    """(dark, accent) resolved like the C++ shell: an explicit ``[appearance] accent``
    wins, else the active ``[world] id``'s accent, else Harbor teal — so a
    world-themed desktop resolves correctly instead of coming back unset."""
    settings = QSettings(path or hede_conf_path(), QSettings.IniFormat)
    dark = _resolve_dark(settings)
    accent = QColor(str(settings.value("appearance/accent", "")).strip())
    if not accent.isValid():
        world_id = str(settings.value("world/id", "harbor")).strip() or "harbor"
        accent = world_accent(world_id)
    if not accent.isValid():
        accent = harbor_accent()
    return dark, accent


def apply_appearance(app: QApplication | None = None, *, path: str | None = None) -> bool:
    """Apply the Helm Fusion + palette + glass QSS to ``app`` when running under HeDE
    (a ``hede.conf`` exists). Returns False and changes nothing otherwise — a plain
    Control Center outside HeDE keeps its native look. Now applies the **stylesheet**
    too (the piece that was missing), so the world glass actually shows."""
    conf = path or hede_conf_path()
    if not os.path.exists(conf):
        return False  # not under HeDE → keep the native look
    dark, accent = read_appearance(conf)
    app = app or QApplication.instance()
    if isinstance(app, QApplication):
        app.setStyle("Fusion")  # honours a custom palette
        app.setStyleSheet(style_sheet(accent))
    QGuiApplication.setPalette(build_palette(dark, accent))
    return True
