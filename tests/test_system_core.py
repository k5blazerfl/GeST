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


def test_current_locale_reads_first_present(tmp_path):
    f = tmp_path / "02locale"
    f.write_text('LANG="fr_FR.UTF-8"\n')
    assert locale.current_locale((str(f), str(tmp_path / "missing"))) == "fr_FR.UTF-8"
    assert os.path.exists(f)
