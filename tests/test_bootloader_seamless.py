"""Tests for the installed-system seamless-boot config
(gest.core.bootloader.seamless): the pure /etc/default/grub transform + the
theme-staging steps."""

from gest.core.bootloader import seamless


def test_grub_settings_has_quiet_splash_and_theme():
    s = seamless.grub_settings()
    assert "quiet" in s["GRUB_CMDLINE_LINUX_DEFAULT"]
    assert "splash" in s["GRUB_CMDLINE_LINUX_DEFAULT"]
    assert s["GRUB_TERMINAL_OUTPUT"] == "gfxterm"
    assert s["GRUB_THEME"] == seamless.THEME_TXT


def test_apply_appends_to_empty():
    out = seamless.apply_grub_default("", {"GRUB_TIMEOUT": "5"})
    assert 'GRUB_TIMEOUT="5"' in out
    assert out.endswith("\n")


def test_apply_replaces_existing_in_place():
    existing = 'GRUB_TIMEOUT="30"\nGRUB_DISTRIBUTOR="Gentoo"\n'
    out = seamless.apply_grub_default(existing, {"GRUB_TIMEOUT": "5"})
    assert 'GRUB_TIMEOUT="5"' in out
    assert 'GRUB_TIMEOUT="30"' not in out
    assert 'GRUB_DISTRIBUTOR="Gentoo"' in out  # untouched
    assert out.count("GRUB_TIMEOUT") == 1       # replaced in place, not duplicated


def test_apply_replaces_commented_key():
    out = seamless.apply_grub_default("#GRUB_THEME=\n", {"GRUB_THEME": "/x/theme.txt"})
    assert 'GRUB_THEME="/x/theme.txt"' in out
    assert out.count("GRUB_THEME") == 1


def test_apply_is_idempotent():
    settings = seamless.grub_settings()
    once = seamless.apply_grub_default('GRUB_DISTRIBUTOR="Gentoo"\n', settings)
    twice = seamless.apply_grub_default(once, settings)
    assert once == twice


def test_grub_default_uses_settings():
    out = seamless.grub_default("")
    assert seamless.SEAMLESS_CMDLINE in out
    assert seamless.THEME_TXT in out


def test_stage_theme_steps_argv():
    steps = seamless.stage_theme_steps()
    cp = next(s for s in steps if s.argv[0] == "cp")
    assert seamless.THEME_SRC in cp.argv and seamless.THEME_DST in cp.argv
    ply = next(s for s in steps if s.argv[0] == "plymouth-set-default-theme")
    assert ply.argv[1] == "hede"


def test_stage_theme_steps_root_prefix():
    steps = seamless.stage_theme_steps(root="/mnt/gentoo")
    cp = next(s for s in steps if s.argv[0] == "cp")
    assert "/mnt/gentoo/boot/grub/themes/hede" in cp.argv
