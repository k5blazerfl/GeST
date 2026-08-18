"""CI-safe tests for the eselect core (pure parsing + argv builder)."""

import pytest

from gest.core.eselect import commands, reader

_MODULES = (
    "Built-in modules:\n"
    "  help                      Display a help message\n"
    "  version                   Display version information\n"
    "\n"
    "Extra modules:\n"
    "  kernel                    Manage the /usr/src/linux symlink\n"
    "  dotnet                    Eselect module for management of multiple dotnet\n"
    "                            versions\n"
    "  profile                   Manage the make.profile symlink\n"
)

_TARGETS = (
    "Available kernel symlink targets:\n"
    "  [1]   linux-6.12.5-gentoo\n"
    "  [2]   linux-7.1.5-gentoo-dist *\n"
)


def test_parse_modules_skips_builtins_and_wraps():
    mods = reader.parse_modules(_MODULES)
    names = [m.name for m in mods]
    assert names == ["kernel", "dotnet", "profile"]   # help/version skipped
    assert "versions" not in names                     # wrapped desc line ignored
    assert dict((m.name, m.description) for m in mods)["kernel"].startswith("Manage")


def test_parse_targets_marks_current():
    ts = reader.parse_targets(_TARGETS)
    assert [(t.number, t.name, t.current) for t in ts] == [
        (1, "linux-6.12.5-gentoo", False),
        (2, "linux-7.1.5-gentoo-dist", True),
    ]


def test_parse_targets_skips_free_form():
    ts = reader.parse_targets("  [1]   nano *\n  [ ]   (free form)\n")
    assert [t.name for t in ts] == ["nano"]


def test_set_argv():
    assert commands.set_argv("kernel", 2) == ["eselect", "kernel", "set", "2"]
    assert commands.set_argv("python", "3", eselect="/usr/bin/eselect")[0] == "/usr/bin/eselect"


def test_set_argv_accepts_a_profile_name():
    # `eselect profile set` also takes a path, not just a list number.
    assert commands.set_argv("profile", "default/linux/amd64/23.0/systemd") == [
        "eselect", "profile", "set", "default/linux/amd64/23.0/systemd"]


@pytest.mark.parametrize("mod,tgt", [
    ("Bad", "1"),        # bad module (uppercase)
    ("k;rm", "1"),       # bad module (metachar)
    ("kernel", "x y"),   # space in the target name
    ("kernel", "a;b"),   # metachar in the target
    ("kernel", "a/../b"),  # traversal in the name
    ("kernel", ""),      # empty target
])
def test_set_argv_rejects(mod, tgt):
    with pytest.raises(ValueError):
        commands.set_argv(mod, tgt)
