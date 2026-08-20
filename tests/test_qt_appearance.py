"""Tests for the Appearance helpers (Qt-free)."""

from gest.qt.appearance import (
    World,
    boot_sync_target,
    parse_worlds,
    read_appearance,
    read_boot_sync,
    read_world,
    set_boot_sync_text,
    theme_args,
    world_args,
    write_boot_sync,
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


def test_read_boot_sync_default_true(tmp_path):
    # opt-out: absent file or missing key → tracking on
    assert read_boot_sync(str(tmp_path / "missing.conf")) is True
    conf = tmp_path / "hede.conf"
    conf.write_text("[world]\nid=harbor\n")
    assert read_boot_sync(str(conf)) is True


def test_read_boot_sync_explicit_false(tmp_path):
    conf = tmp_path / "hede.conf"
    conf.write_text("[boot]\nsync_with_biome=false\n")
    assert read_boot_sync(str(conf)) is False


def test_set_boot_sync_text_appends_section():
    out = set_boot_sync_text("[world]\nid=harbor\n", False)
    assert "[world]\nid=harbor" in out          # untouched
    assert "[boot]\nsync_with_biome=false" in out
    assert out.endswith("\n")


def test_set_boot_sync_text_replaces_in_place():
    existing = "[boot]\nsync_with_biome=false\n[world]\nid=harbor\n"
    out = set_boot_sync_text(existing, True)
    assert "sync_with_biome=true" in out
    assert "sync_with_biome=false" not in out
    assert out.count("sync_with_biome") == 1     # replaced, not duplicated
    assert "[world]\nid=harbor" in out           # later section preserved


def test_set_boot_sync_text_inserts_into_existing_section():
    existing = "[boot]\nother=1\n[world]\nid=harbor\n"
    out = set_boot_sync_text(existing, True)
    assert "other=1" in out                      # sibling key kept
    assert "sync_with_biome=true" in out
    # inserted under [boot], before [world]
    assert out.index("sync_with_biome") < out.index("[world]")


def test_set_boot_sync_text_roundtrip_stable():
    once = set_boot_sync_text("", True)
    assert set_boot_sync_text(once, True) == once   # idempotent


def test_write_and_read_boot_sync_roundtrip(tmp_path):
    conf = tmp_path / "hede.conf"
    conf.write_text("[appearance]\ndark=true\naccent=#e8853a\n[world]\nid=emberforge\n")
    write_boot_sync(str(conf), False)
    assert read_boot_sync(str(conf)) is False
    # existing sections survive the surgical write
    assert read_appearance(str(conf)) == (True, "#e8853a")
    assert read_world(str(conf)) == "emberforge"


def test_boot_sync_target_reads_accent_and_world(tmp_path):
    conf = tmp_path / "hede.conf"
    conf.write_text("[appearance]\naccent=#5fd0dd\n[world]\nid=stormwatch\n")
    assert boot_sync_target(str(conf)) == ("#5fd0dd", "stormwatch")


def test_boot_sync_target_defaults(tmp_path):
    # no explicit accent → "" (backend derives from world); no world → harbor
    conf = tmp_path / "hede.conf"
    conf.write_text("[appearance]\ndark=true\n")
    assert boot_sync_target(str(conf)) == ("", "harbor")
