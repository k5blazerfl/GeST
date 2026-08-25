"""Pure catalog + argv coverage for the default-web-browser control."""

from gest.core.defaultapps import browser as b


def test_catalog_is_coherent():
    assert b.BROWSERS, "catalog must not be empty"
    # exactly one recommended default leads the list
    recommended = [x for x in b.BROWSERS if x.recommended]
    assert len(recommended) == 1
    assert b.BROWSERS[0].recommended
    # ids / desktop ids / atoms are all unique
    for field in ("id", "desktop_id", "atom"):
        values = [getattr(x, field) for x in b.BROWSERS]
        assert len(values) == len(set(values)), f"duplicate {field}"


def test_bin_first_for_heavy_browsers():
    # a casual pick must never kick off a source Chromium build
    for x in b.BROWSERS:
        assert x.atom.startswith("www-client/")


def test_chrome_and_opera_are_offered_with_their_eula_licenses():
    chrome = b.by_id("chrome")
    opera = b.by_id("opera")
    assert chrome is not None and opera is not None
    assert chrome.atom == "www-client/google-chrome" and chrome.license == "google-chrome"
    assert opera.atom == "www-client/opera" and opera.license == "OPERA-2018"
    assert opera.desktop_id == "opera"


def test_free_browsers_declare_no_license():
    # Firefox/Chromium are free — nothing to accept, so no package.license write
    assert b.by_id("firefox").license == ""


def test_by_id_and_by_desktop_id():
    firefox = b.by_id("firefox")
    assert firefox is not None and firefox.name == "Firefox"
    assert b.by_id("nope") is None
    # tolerate present-or-absent .desktop suffix
    assert b.by_desktop_id("firefox.desktop") is firefox
    assert b.by_desktop_id("firefox") is firefox
    assert b.by_desktop_id("konqueror.desktop") is None


def test_argv_shapes():
    assert b.get_default_argv() == ["xdg-settings", "get", "default-web-browser"]
    # suffix is ensured whether or not the caller supplied it
    assert b.set_default_argv("firefox") == [
        "xdg-settings", "set", "default-web-browser", "firefox.desktop",
    ]
    assert b.set_default_argv("firefox.desktop")[-1] == "firefox.desktop"


def test_parse_default():
    assert b.parse_default("firefox.desktop\n") is b.by_id("firefox")
    assert b.parse_default("") is None
    assert b.parse_default("something-we-dont-ship.desktop") is None


def test_probe_paths_and_is_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "_APP_DIRS", (str(tmp_path),))
    firefox = b.by_id("firefox")
    paths = b.desktop_probe_paths(firefox)
    assert paths == [tmp_path / "firefox.desktop"]
    assert b.is_installed(firefox) is False
    (tmp_path / "firefox.desktop").write_text("[Desktop Entry]\n")
    assert b.is_installed(firefox) is True
