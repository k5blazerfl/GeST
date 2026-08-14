"""Tests for the Appearance helpers (Qt-free)."""

from gest.qt.appearance import read_appearance, theme_args


def test_theme_args_light_and_dark():
    assert theme_args(False) == ["--light"]
    assert theme_args(True) == ["--dark"]


def test_theme_args_full():
    assert theme_args(True, "#33d6c8", "Adwaita-dark", "Papirus") == [
        "--dark",
        "--accent=#33d6c8",
        "--gtk-theme=Adwaita-dark",
        "--icon-theme=Papirus",
    ]


def test_read_appearance_roundtrip(tmp_path):
    conf = tmp_path / "hede.conf"
    conf.write_text("[appearance]\ndark=true\naccent=#33d6c8\n")
    assert read_appearance(str(conf)) == (True, "#33d6c8")


def test_read_appearance_defaults(tmp_path):
    assert read_appearance(str(tmp_path / "missing.conf")) == (False, "")
