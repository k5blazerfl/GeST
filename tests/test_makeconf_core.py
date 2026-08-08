"""CI-safe tests for the make.conf parser/renderer."""

import pytest

from gest.core.makeconf import reader

_SAMPLE = (
    "# a comment\n"
    'COMMON_FLAGS="-O2 -pipe"\n'
    'CFLAGS="${COMMON_FLAGS}"\n'
    "LC_MESSAGES=C.UTF-8\n"
    'GENTOO_MIRRORS="https://a/ \\\n'
    '\t\thttps://b/ \\\n'
    '\t\thttps://c/"\n'
    'USE="bluetooth"\n'
    'USE="networkmanager"\n'
)


def test_variables_effective_and_preserves_refs():
    by = {v.name: v.value for v in reader.variables(_SAMPLE)}
    assert by["CFLAGS"] == "${COMMON_FLAGS}"          # ref preserved, not expanded
    assert by["LC_MESSAGES"] == "C.UTF-8"             # unquoted
    assert by["USE"] == "networkmanager"              # last assignment wins
    assert by["GENTOO_MIRRORS"] == "https://a/ https://b/ https://c/"  # multi-line collapsed


def test_render_replaces_last_and_keeps_rest():
    out = reader.render(_SAMPLE, "USE", "networkmanager bluetooth")
    assert 'USE="networkmanager bluetooth"' in out
    assert 'CFLAGS="${COMMON_FLAGS}"' in out          # untouched
    assert "https://c/" in out                         # mirrors untouched
    assert reader.variables(out)[-1] == reader.Var("USE", "networkmanager bluetooth") \
        or {v.name: v.value for v in reader.variables(out)}["USE"] == "networkmanager bluetooth"


def test_render_appends_new_variable():
    out = reader.render(_SAMPLE, "MAKEOPTS", "-j8")
    assert out.rstrip().endswith('MAKEOPTS="-j8"')
    assert {v.name: v.value for v in reader.variables(out)}["MAKEOPTS"] == "-j8"


def test_validators():
    assert reader.valid_name("MAKEOPTS") and not reader.valid_name("2BAD")
    assert reader.valid_value("${COMMON_FLAGS} -O2")   # refs ok
    assert not reader.valid_value('has"quote')
    assert not reader.valid_value("cmd`sub`")
    assert not reader.valid_value("cmd$(sub)")
    assert not reader.valid_value("line\nbreak")


@pytest.mark.parametrize("name", ["", "1x", "a b", "x-y"])
def test_invalid_names(name):
    assert not reader.valid_name(name)
