"""Pure tests for the @world deselect + package-set helpers (no Portage/D-Bus)."""

import pytest

from gest.core.software import sets, world


def test_deselect_argv_builds_emerge_command():
    argv = world.deselect_argv(["app-misc/neofetch", "games-board/freecell"])
    assert argv == ["emerge", "--deselect", "--color", "n",
                    "app-misc/neofetch", "games-board/freecell"]


def test_deselect_argv_honours_emerge_path():
    argv = world.deselect_argv(["a/b"], emerge="/usr/bin/emerge")
    assert argv[0] == "/usr/bin/emerge"


@pytest.mark.parametrize("atom", [
    "dev-lang/python",
    "dev-lang/python:3.11",       # slotted
    "=cat/pkg-1.2",               # version-pinned
    ">=dev-libs/foo-2",           # version operator
])
def test_valid_atom_accepts_real_atoms(atom):
    assert world.valid_atom(atom)


@pytest.mark.parametrize("atom", [
    "--root=/etc",                # option-looking (leading dash)
    "cat/pkg; rm -rf /",          # metacharacters / whitespace
    "cat pkg",
    "",
])
def test_valid_atom_rejects_unsafe(atom):
    assert not world.valid_atom(atom)


@pytest.mark.parametrize("atoms", [[], ["--root=/etc"], ["ok/pkg", "bad atom"]])
def test_deselect_argv_rejects_bad_input(atoms):
    with pytest.raises(ValueError):
        world.deselect_argv(atoms)


# -- package sets -----------------------------------------------------------

def test_read_set_file_skips_blanks_and_comments(tmp_path):
    f = tmp_path / "myset"
    f.write_text("# a comment\nx11-wm/i3\n\napp-editors/neovim\n")
    assert sets.read_set_file(str(f)) == ["x11-wm/i3", "app-editors/neovim"]


def test_read_set_file_missing_is_empty(tmp_path):
    assert sets.read_set_file(str(tmp_path / "nope")) == []


def test_custom_sets_lists_files_as_named_sets(tmp_path):
    (tmp_path / "desktop").write_text("x11-wm/i3\n")
    (tmp_path / "media").write_text("media-video/mpv\napp-misc/foo\n")
    (tmp_path / ".hidden").write_text("ignored\n")   # dotfiles skipped
    (tmp_path / "sub").mkdir()                        # directories skipped
    result = sets.custom_sets(str(tmp_path))
    assert [(s.name, s.atoms, s.kind) for s in result] == [
        ("@desktop", ["x11-wm/i3"], "custom"),
        ("@media", ["media-video/mpv", "app-misc/foo"], "custom"),
    ]


def test_custom_sets_missing_dir_is_empty():
    assert sets.custom_sets("/nonexistent/portage/sets") == []


# -- editing custom sets ----------------------------------------------------

@pytest.mark.parametrize("name,ok", [
    ("mydesktop", True), ("media2", True), ("my-set.list", True),
    ("../etc", False), ("has space", False), ("", False), (".hidden", False),
])
def test_valid_set_name(name, ok):
    assert sets.valid_set_name(name) is ok


@pytest.mark.parametrize("entry,ok", [
    ("app-editors/vim", True), ("=cat/pkg-1.2", True),
    ("dev-lang/python:3.11", True), ("@world", True),
    ("rm -rf /", False), ("--root=/", False), ("@bad set", False), ("", False),
])
def test_valid_entry(entry, ok):
    assert sets.valid_entry(entry) is ok


def test_set_path_is_under_sets_dir():
    assert sets.set_path("media") == "/etc/portage/sets/media"
    assert sets.set_path("media", "/tmp/s") == "/tmp/s/media"


def test_render_set_roundtrips_through_reader(tmp_path):
    p = tmp_path / "media"
    p.write_text(sets.render_set(["x11-wm/i3", "@gui"]))
    assert sets.read_set_file(str(p)) == ["x11-wm/i3", "@gui"]


def test_render_empty_set_is_a_nonempty_file(tmp_path):
    # empty text would mean "delete"; an empty set must still write a file
    body = sets.render_set([])
    assert body.strip() != ""
    p = tmp_path / "empty"
    p.write_text(body)
    assert sets.read_set_file(str(p)) == []


# -- PendingSets (staged edits) ---------------------------------------------

def test_pending_starts_empty():
    p = sets.PendingSets({"media": ["media-video/mpv"]})
    assert p.is_empty() and p.count() == 0
    assert p.working_atoms("media") == ["media-video/mpv"]   # falls back to disk
    assert not p.is_modified("media")


def test_pending_modify_and_normalize():
    p = sets.PendingSets({"media": ["a/b"]})
    p.set_atoms("media", ["a/b", "c/d"])
    assert p.is_modified("media") and not p.is_new("media")
    assert p.working_atoms("media") == ["a/b", "c/d"]
    assert [(e.name, e.kind, e.atoms) for e in p.edits()] == [
        ("media", sets.MODIFY, ["a/b", "c/d"])]
    p.set_atoms("media", ["a/b"])                            # back to baseline
    assert not p.is_modified("media") and p.is_empty()


def test_pending_create_and_delete():
    p = sets.PendingSets({"media": ["a/b"]})
    p.set_atoms("newset", ["x/y"])                          # create
    p.toggle_delete("media")                                # delete existing
    assert p.is_new("newset") and p.is_deleted("media")
    assert p.working_atoms("media") is None                 # deleted → None
    assert p.count() == 2
    kinds = {e.name: e.kind for e in p.edits()}
    assert kinds == {"newset": sets.NEW, "media": sets.DELETE}


def test_pending_toggle_delete_cancels_new_and_restores_existing():
    p = sets.PendingSets({"media": ["a/b"]})
    p.set_atoms("newset", ["x/y"])
    p.toggle_delete("newset")                               # delete an unsaved new = cancel
    assert not p.is_modified("newset")
    p.toggle_delete("media")
    p.toggle_delete("media")                                # un-delete
    assert not p.is_deleted("media") and p.is_empty()


def test_pending_exists_and_clear():
    p = sets.PendingSets({"media": ["a/b"]})
    p.set_atoms("newset", ["x/y"])
    assert p.exists("media") and p.exists("newset") and not p.exists("nope")
    p.clear()
    assert p.is_empty() and not p.exists("newset")
