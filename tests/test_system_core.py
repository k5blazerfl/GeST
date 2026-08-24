"""CI-safe tests for the System module core (hostname/timezone/locale)."""

import os

import pytest

from gest.core.system import hostname, locale, timezone


@pytest.mark.parametrize("good", ["host", "my-host", "a.b.example.com", "h1"])
def test_valid_hostname_accepts(good):
    assert hostname.valid_hostname(good)


@pytest.mark.parametrize("bad", ["", "bad host", "-lead", "trail-", "a..b", "x" * 300])
def test_valid_hostname_rejects(bad):
    assert not hostname.valid_hostname(bad)


def test_parse_conf_hostname():
    assert hostname.parse_conf_hostname('hostname="tux"\n') == "tux"
    assert hostname.parse_conf_hostname("hostname=plainval  # comment\n") == "plainval"
    assert hostname.parse_conf_hostname("# nothing here\n") == ""


def test_valid_zone_name():
    assert timezone.valid_zone_name("America/New_York")
    assert timezone.valid_zone_name("UTC")
    assert not timezone.valid_zone_name("../etc/passwd")
    assert not timezone.valid_zone_name("has space")


def test_list_zones_from_tmp(tmp_path):
    (tmp_path / "America").mkdir()
    (tmp_path / "America" / "New_York").write_text("TZ")
    (tmp_path / "UTC").write_text("TZ")
    (tmp_path / "iso3166.tab").write_text("data")  # skipped (has extension)
    (tmp_path / "posix").mkdir()
    (tmp_path / "posix" / "UTC").write_text("TZ")  # skipped subdir
    zones = timezone.list_zones(str(tmp_path))
    assert "America/New_York" in zones and "UTC" in zones
    assert "iso3166.tab" not in zones
    assert not any(z.startswith("posix") for z in zones)


def test_locale_validate_and_parse():
    assert locale.valid_locale("en_US.UTF-8")
    assert not locale.valid_locale("bad locale!")
    assert locale.parse_lang('LANG="de_DE.UTF-8"\n') == "de_DE.UTF-8"
    assert locale.parse_lang("LANG=C.UTF-8\n") == "C.UTF-8"


def test_list_locales_with_runner():
    out = locale.list_locales(lambda argv: "C\nen_US.utf8\nen_US.utf8\n")
    assert out == ["C", "en_US.utf8"]


def test_locale_gen_line():
    # /etc/locale.gen entry to compile a chosen LANG; None for glibc built-ins.
    assert locale.locale_gen_line("en_US.UTF-8") == "en_US.UTF-8 UTF-8"
    assert locale.locale_gen_line("en_US.utf8") == "en_US.UTF-8 UTF-8"   # glibc form
    assert locale.locale_gen_line("de_DE.ISO-8859-15") == "de_DE.ISO-8859-15 ISO-8859-15"
    assert locale.locale_gen_line("C.UTF-8") is None          # built-in
    assert locale.locale_gen_line("C") is None
    assert locale.locale_gen_line("POSIX") is None
    assert locale.locale_gen_line("de_DE") is None            # no charset → skip


def test_locale_match_in_bridges_utf8_notation():
    # `locale -a` emits glibc's `.utf8`; stored/default locales use `.UTF-8`. The
    # two denote the same locale — match_in resolves across the notation so a picker
    # can highlight the current value (the Language/Locale submenu regression).
    choices = ["C", "C.utf8", "POSIX", "en_US.utf8"]
    assert locale.match_in("C.UTF-8", choices) == "C.utf8"
    assert locale.match_in("en_US.UTF-8", choices) == "en_US.utf8"
    assert locale.match_in("C.utf8", choices) == "C.utf8"        # already-listed form
    assert locale.match_in("POSIX", choices) == "POSIX"          # no encoding suffix
    assert locale.match_in("de_DE.UTF-8", choices) == "de_DE.UTF-8"  # absent → unchanged
    assert locale.canonical_key("C.UTF-8") == locale.canonical_key("C.utf8")


def test_current_locale_reads_first_present(tmp_path):
    f = tmp_path / "02locale"
    f.write_text('LANG="fr_FR.UTF-8"\n')
    assert locale.current_locale((str(f), str(tmp_path / "missing"))) == "fr_FR.UTF-8"
    assert os.path.exists(f)


def test_current_timezone_falls_back_to_localtime_symlink(tmp_path):
    from gest.core.system import timezone
    zoneinfo = tmp_path / "zoneinfo"
    (zoneinfo / "America").mkdir(parents=True)
    (zoneinfo / "America" / "New_York").write_text("TZif")
    localtime = tmp_path / "localtime"
    localtime.symlink_to(zoneinfo / "America" / "New_York")
    # no /etc/timezone -> resolves the symlink into a zone name
    tz = timezone.current_timezone(
        path=str(tmp_path / "nope"), localtime=str(localtime), zoneinfo=str(zoneinfo))
    assert tz == "America/New_York"
