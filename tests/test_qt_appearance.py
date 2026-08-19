"""Tests for the Appearance helpers (Qt-free)."""

from gest.qt.appearance import (
    World,
    parse_worlds,
    read_appearance,
    read_world,
    theme_args,
    world_args,
)


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


def test_world_args():
    assert world_args("emberforge") == ["--world=emberforge"]


def test_parse_worlds_full():
    out = (
        "harbor\tHarbor\t#3aa6c4\t/usr/share/hede/worlds/harbor/wallpaper.png\n"
        "emberforge\tEmberforge\t#e8853a\t/usr/share/hede/worlds/emberforge/wallpaper.png\n"
    )
    worlds = parse_worlds(out)
    assert worlds == [
        World("harbor", "Harbor", "#3aa6c4", "/usr/share/hede/worlds/harbor/wallpaper.png"),
        World(
            "emberforge",
            "Emberforge",
            "#e8853a",
            "/usr/share/hede/worlds/emberforge/wallpaper.png",
        ),
    ]


def test_parse_worlds_tolerates_missing_fields_and_blanks():
    # missing trailing fields default empty; blank/id-less lines skipped;
    # a name-less row falls back to the id.
    out = "harbor\tHarbor\n\nmistreef\n\t\tignored\n"
    worlds = parse_worlds(out)
    assert worlds == [World("harbor", "Harbor", "", ""), World("mistreef", "mistreef", "", "")]


def test_read_world_roundtrip(tmp_path):
    conf = tmp_path / "hede.conf"
    conf.write_text("[world]\nid=stormwatch\n")
    assert read_world(str(conf)) == "stormwatch"


def test_read_world_defaults_to_harbor(tmp_path):
    assert read_world(str(tmp_path / "missing.conf")) == "harbor"
