"""Tests for the Helm-appearance consumer (leg 3A): the palette port + the
hede.conf read, so the Control Center matches the shell's buildPalette/applyAppearance.
"""

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from gest.qt.theme import (
    apply_appearance,
    build_palette,
    contrast_text,
    fixed_font,
    read_appearance,
)


def _app():
    return QApplication.instance() or QApplication([])


def test_contrast_text():
    assert contrast_text(QColor("#ffffff")) == QColor(Qt.black)
    assert contrast_text(QColor("#000000")) == QColor(Qt.white)


def test_build_palette_dark_and_accent():
    _app()
    accent = QColor("#3b82f6")
    p = build_palette(True, accent)
    assert p.color(QPalette.Window) == QColor(0x2B, 0x2B, 0x2B)
    assert p.color(QPalette.Base) == QColor(0x1E, 0x1E, 0x1E)
    assert p.color(QPalette.Highlight) == accent
    assert p.color(QPalette.HighlightedText) == contrast_text(accent)


def test_build_palette_light_no_accent_leaves_defaults():
    _app()
    p = build_palette(False, QColor())  # invalid accent → no override
    assert p.color(QPalette.Highlight) == QPalette().color(QPalette.Highlight)


def test_read_and_apply_appearance(tmp_path):
    app = _app()
    saved = app.palette()
    conf = str(tmp_path / "hede" / "hede.conf")
    settings = QSettings(conf, QSettings.IniFormat)
    settings.setValue("appearance/dark", True)
    settings.setValue("appearance/accent", "#3b82f6")
    settings.sync()
    try:
        dark, accent = read_appearance(conf)
        assert dark is True and accent == QColor("#3b82f6")
        assert apply_appearance(app, path=conf) is True
    finally:
        app.setPalette(saved)  # don't leak the themed palette to other tests


def test_apply_appearance_is_noop_when_unthemed(tmp_path):
    app = _app()
    empty = str(tmp_path / "none.conf")
    dark, accent = read_appearance(empty)
    assert dark is False and not accent.isValid()
    assert apply_appearance(app, path=empty) is False


def test_fixed_font_is_a_font():
    _app()
    assert isinstance(fixed_font(), QFont)
