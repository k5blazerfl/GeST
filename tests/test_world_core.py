"""Pure tests for the @world deselect helpers (no Portage, no D-Bus)."""

import pytest

from gest.core.software import world


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
