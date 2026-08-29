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
    harbor_accent,
    read_appearance,
    style_sheet,
    world_accent,
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


def test_apply_appearance_is_noop_without_a_hede_conf(tmp_path):
    # Not under HeDE (no hede.conf) → keep the native look, change nothing.
    app = _app()
    missing = str(tmp_path / "none.conf")
    assert apply_appearance(app, path=missing) is False


def test_read_appearance_resolves_mode_and_world_accent(tmp_path, monkeypatch):
    _app()
    # a world-themed desktop: [appearance] mode=dark, no explicit accent, world=slate
    worlds = tmp_path / "worlds"
    (worlds / "slate").mkdir(parents=True)
    (worlds / "slate" / "theme.yaml").write_text("accent: '#5f7d9c'\n", encoding="utf-8")
    monkeypatch.setattr("gest.qt.theme._world_dirs", lambda: [str(worlds)])
    conf = str(tmp_path / "hede" / "hede.conf")
    s = QSettings(conf, QSettings.IniFormat)
    s.setValue("appearance/mode", "dark")
    s.setValue("world/id", "slate")
    s.sync()
    dark, accent = read_appearance(conf)
    assert dark is True                      # mode=dark (not the legacy bool)
    assert accent == QColor("#5f7d9c")       # resolved from the active world


def test_read_appearance_falls_back_to_harbor(tmp_path, monkeypatch):
    _app()
    monkeypatch.setattr("gest.qt.theme._world_dirs", lambda: [str(tmp_path / "none")])
    conf = str(tmp_path / "hede" / "hede.conf")
    QSettings(conf, QSettings.IniFormat).sync()   # empty config
    dark, accent = read_appearance(conf)
    assert dark is False and accent == harbor_accent()


def test_world_accent_reads_the_theme_yaml(tmp_path):
    _app()
    (tmp_path / "harbor").mkdir()
    (tmp_path / "harbor" / "theme.yaml").write_text(
        "# comment\naccent: '#3aa6c4'\n", encoding="utf-8")
    assert world_accent("harbor", dirs=[str(tmp_path)]) == QColor("#3aa6c4")
    assert not world_accent("missing", dirs=[str(tmp_path)]).isValid()


def test_style_sheet_tints_chrome_with_the_accent():
    _app()
    qss = style_sheet(harbor_accent())
    # the app-chrome selectors the Control Center relies on are present…
    assert "#HelmAppWindow QMenuBar" in qss and "#HelmAppWindow QToolBar" in qss
    # …and the accent is substituted into the selection fill (harbor = 58,166,196)
    assert "rgba(58,166,196,0.34)" in qss
    # a different accent changes the tint
    assert "rgba(58,166,196" not in style_sheet(QColor("#ff0000"))


def test_apply_appearance_installs_stylesheet(tmp_path):
    app = _app()
    saved_qss, saved_pal = app.styleSheet(), app.palette()
    conf = str(tmp_path / "hede" / "hede.conf")
    s = QSettings(conf, QSettings.IniFormat)
    s.setValue("appearance/accent", "#3b82f6")
    s.sync()
    try:
        assert apply_appearance(app, path=conf) is True
        assert "#HelmAppWindow" in app.styleSheet()      # the missing piece, now applied
    finally:
        app.setStyleSheet(saved_qss)
        app.setPalette(saved_pal)


def test_fixed_font_is_a_font():
    _app()
    assert isinstance(fixed_font(), QFont)
