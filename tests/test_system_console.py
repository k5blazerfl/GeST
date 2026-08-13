"""CI-safe tests for the console keymap/font core: validation, conf.d upsert
(preserving other keys), current-value parsing, and listing over a fixture tree."""

from gest.core.system import console

# --- validation -------------------------------------------------------------

def test_valid_keymap_and_font():
    for good in ("us", "de-latin1", "uk", "ter-v16n", "default8x16", "lat9w-16"):
        assert console.valid_keymap(good)
        assert console.valid_font(good)
    for bad in ("", "us; rm -rf /", "a b", 'x"', "../etc", "-leading"):
        assert not console.valid_keymap(bad)
        assert not console.valid_font(bad)


# --- conf.d parse / upsert --------------------------------------------------

def test_parse_conf_value():
    assert console.parse_conf_value('keymap="us"\n', "keymap") == "us"
    assert console.parse_conf_value("consolefont=ter-v16n\n", "consolefont") == "ter-v16n"
    assert console.parse_conf_value("# nothing here\n", "keymap") == ""


def test_set_conf_value_replaces_in_place_preserving_other_lines():
    text = 'keymap="us"\nwindowkeys="YES"\nkeymap_first="NO"\n'
    out = console.set_conf_value(text, "keymap", "de-latin1")
    assert 'keymap="de-latin1"' in out
    assert 'windowkeys="YES"' in out          # untouched
    assert 'keymap_first="NO"' in out         # not clobbered by the keymap= match
    assert out.count('keymap="') == 1         # only the real keymap line, no duplicate


def test_set_conf_value_appends_when_absent():
    assert console.set_conf_value("# empty\n", "keymap", "uk") == '# empty\nkeymap="uk"\n'
    assert console.set_conf_value("", "consolefont", "ter-v16n") == 'consolefont="ter-v16n"\n'
    # no missing newline when the file lacks a trailing one
    assert console.set_conf_value('a="b"', "keymap", "us") == 'a="b"\nkeymap="us"\n'


# --- current values ---------------------------------------------------------

def test_current_keymap_and_font_read_conf_files(tmp_path):
    kb = tmp_path / "keymaps"
    kb.write_text('keymap="fr"\n')
    cf = tmp_path / "consolefont"
    cf.write_text('consolefont="lat9w-16"\n')
    assert console.current_keymap(str(kb)) == "fr"
    assert console.current_font(str(cf)) == "lat9w-16"
    assert console.current_keymap(str(tmp_path / "missing")) == ""


# --- listing ----------------------------------------------------------------

def test_strip_suffix_longest_first():
    assert console._strip_suffix("us.map.gz", console._KEYMAP_SUFFIXES) == "us"
    assert console._strip_suffix("ter-v16n.psf.gz", console._FONT_SUFFIXES) == "ter-v16n"
    assert console._strip_suffix("default8x16.gz", console._FONT_SUFFIXES) == "default8x16"
    assert console._strip_suffix("plain", console._KEYMAP_SUFFIXES) == "plain"


def test_list_keymaps_over_a_fixture_tree(tmp_path):
    (tmp_path / "i386" / "qwerty").mkdir(parents=True)
    (tmp_path / "i386" / "qwerty" / "us.map.gz").write_bytes(b"")
    (tmp_path / "i386" / "qwerty" / "uk.map.gz").write_bytes(b"")
    (tmp_path / "mac").mkdir()
    (tmp_path / "mac" / "mac-us.map.gz").write_bytes(b"")
    assert console.list_keymaps(str(tmp_path)) == ["mac-us", "uk", "us"]


def test_list_fonts_over_a_fixture_tree(tmp_path):
    (tmp_path / "ter-v16n.psf.gz").write_bytes(b"")
    (tmp_path / "default8x16.psfu.gz").write_bytes(b"")
    assert console.list_fonts(str(tmp_path)) == ["default8x16", "ter-v16n"]
