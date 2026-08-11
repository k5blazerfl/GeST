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
