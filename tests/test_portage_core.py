"""CI-safe tests for the unified Portage config core (pure codecs + helpers)."""

import dataclasses

import pytest

from gest.core.portage import paths, write
from gest.core.portage.codec import atomfile, ini, shell

# --------------------------------------------------------------------------- #
# shell codec (make.conf)
# --------------------------------------------------------------------------- #

_MAKECONF = (
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


def test_shell_variables_effective_and_refs():
    by = {v.name: v.value for v in shell.variables(_MAKECONF)}
    assert by["CFLAGS"] == "${COMMON_FLAGS}"          # ref preserved, not expanded
    assert by["LC_MESSAGES"] == "C.UTF-8"             # unquoted value
    assert by["USE"] == "networkmanager"              # last assignment wins
    assert by["GENTOO_MIRRORS"] == "https://a/ https://b/ https://c/"  # collapsed


def test_shell_render_replaces_in_place_and_appends():
    out = shell.render(_MAKECONF, "USE", "networkmanager bluetooth")
    assert 'USE="networkmanager bluetooth"' in out
    assert 'CFLAGS="${COMMON_FLAGS}"' in out          # untouched
    assert "https://c/" in out                         # mirrors untouched
    assert "# a comment" in out                        # comment preserved
    out2 = shell.render(out, "MAKEOPTS", "-j8")
    assert out2.rstrip().endswith('MAKEOPTS="-j8"')
    assert {v.name: v.value for v in shell.variables(out2)}["MAKEOPTS"] == "-j8"


def test_shell_validators():
    assert shell.valid_name("MAKEOPTS") and not shell.valid_name("2BAD")
    assert shell.valid_value("${COMMON_FLAGS} -O2")
    for bad in ('has"quote', "cmd`sub`", "cmd$(sub)", "line\nbreak"):
        assert not shell.valid_value(bad)


# --------------------------------------------------------------------------- #
# ini codec (repos.conf / binrepos.conf)
# --------------------------------------------------------------------------- #

_REPOS = (
    "[DEFAULT]\nmain-repo = gentoo\n\n"
    "# managed by eselect-repo\n"
    "[gentoo]\nlocation = /var/db/repos/gentoo\nsync-type = rsync\n"
    "sync-uri = rsync://r/gentoo\n\n"
    "[guru]\nsync-type = git\nsync-uri = https://h/guru.git\n"
)


def test_ini_parse_defaults_sections_and_order():
    defaults, sections = ini.parse(_REPOS)
    assert defaults == {"main-repo": "gentoo"}
    assert [s.name for s in sections] == ["gentoo", "guru"]   # order preserved
    assert sections[0].entries["sync-uri"] == "rsync://r/gentoo"
    assert ini.sections_dict(_REPOS)["guru"]["sync-type"] == "git"


def test_ini_render_round_trips_through_parse():
    text = ini.render(
        [ini.Section("gentoo", {"priority": "9959", "sync-uri": "https://d/binpkg"})],
        defaults={"main-repo": "gentoo"},
    )
    assert text.startswith("[DEFAULT]")
    defaults, sections = ini.parse(text)
    assert defaults == {"main-repo": "gentoo"}
    assert sections[0].name == "gentoo"
    assert sections[0].entries["priority"] == "9959"


def test_ini_render_empty_is_empty():
    assert ini.render([]) == ""


# --------------------------------------------------------------------------- #
# atomfile codec (package.*)
# --------------------------------------------------------------------------- #

_ATOMS = (
    "# GeST-managed\n"
    "app-editors/vim -X python\n"
    "\n"
    "sys-kernel/gentoo-sources symlink\n"
)


def test_atomfile_parse_and_lookups():
    rows = atomfile.parse(_ATOMS)
    assert [r.atom for r in rows] == ["app-editors/vim", "sys-kernel/gentoo-sources"]
    assert atomfile.tokens_for(_ATOMS, "app-editors/vim") == ["-X", "python"]
    assert atomfile.line_for(_ATOMS, "sys-kernel/gentoo-sources") == \
        "sys-kernel/gentoo-sources symlink"
    assert atomfile.line_for(_ATOMS, "cat/absent") == ""


def test_atomfile_upsert_replaces_only_target_and_keeps_comments():
    out = atomfile.upsert(_ATOMS, "app-editors/vim", "app-editors/vim X -python")
    assert "app-editors/vim X -python" in out
    assert "-X python" not in out                       # old line dropped
    assert "# GeST-managed" in out                      # comment preserved
    assert atomfile.line_for(out, "sys-kernel/gentoo-sources") == \
        "sys-kernel/gentoo-sources symlink"             # sibling untouched


def test_atomfile_upsert_empty_line_removes_atom():
    out = atomfile.upsert(_ATOMS, "app-editors/vim", "")
    assert atomfile.line_for(out, "app-editors/vim") == ""
    assert atomfile.line_for(out, "sys-kernel/gentoo-sources") != ""
    assert out.endswith("\n")


def test_atomfile_upsert_into_empty_is_terminated():
    assert atomfile.upsert("", "cat/pkg", "cat/pkg flag") == "cat/pkg flag\n"
    assert atomfile.upsert("", "cat/pkg", "") == ""


# --------------------------------------------------------------------------- #
# write value type + path allow-list
# --------------------------------------------------------------------------- #

def test_config_write_defaults_and_frozen():
    cw = write.ConfigWrite("/etc/portage/make.conf", "USE=\"x\"\n")
    assert cw.mode == 0o644
    with pytest.raises(dataclasses.FrozenInstanceError):
        cw.path = "/etc/shadow"                          # frozen


@pytest.mark.parametrize("path", [
    "/etc/portage/make.conf",
    "/etc/portage/package.use/gest",
    "/etc/portage/binrepos.conf/gest.conf",
])
def test_is_within_etc_portage_accepts(path):
    assert write.is_within_etc_portage(path)


@pytest.mark.parametrize("path", [
    "/etc/shadow",
    "/etc/portage/../../etc/shadow",
    "/etc/portagex/make.conf",
    "/etc/portage",   # the dir itself, not a file within it — but allowed as base
])
def test_is_within_etc_portage_rejects_traversal(path):
    if path == "/etc/portage":
        assert write.is_within_etc_portage(path)         # base itself is allowed
    else:
        assert not write.is_within_etc_portage(path)


def test_is_within_etc_portage_honours_root():
    assert write.is_within_etc_portage("/mnt/gentoo/etc/portage/make.conf", root="/mnt/gentoo")
    assert not write.is_within_etc_portage("/etc/portage/make.conf", root="/mnt/gentoo")


# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #

def test_paths_shapes_with_explicit_root():
    assert paths.make_conf("/") == "/etc/portage/make.conf"
    assert paths.gest_fragment("use", "/") == "/etc/portage/package.use/gest"
    assert paths.gest_fragment("accept_keywords", "/mnt") == \
        "/mnt/etc/portage/package.accept_keywords/gest"
    assert paths.binhost_fragment("/") == "/etc/portage/binrepos.conf/gest.conf"
    assert paths.repos_conf_dir("/") == "/etc/portage/repos.conf"
