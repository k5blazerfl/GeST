"""Tests for the pure user/group argv builders (CI-safe)."""

import pytest

from gest.core.users import commands as c


def test_useradd_argv_full():
    argv = c.useradd_argv(
        "alice", comment="Alice Example", shell="/bin/bash", groups="wheel, users"
    )
    assert argv[0] == "useradd"
    assert "--create-home" in argv
    assert argv[-1] == "alice"
    assert argv[argv.index("--groups") + 1] == "wheel,users"


def test_useradd_system_has_no_create_home():
    argv = c.useradd_argv("svc", system=True)
    assert "--system" in argv and "--create-home" not in argv


def test_usermod_requires_a_change():
    with pytest.raises(ValueError):
        c.usermod_argv("alice")
    assert c.usermod_argv("alice", shell="/bin/zsh")[-1] == "alice"


def test_userdel_and_group_builders():
    assert c.userdel_argv("alice", remove_home=True) == ["userdel", "--remove", "alice"]
    assert c.groupadd_argv("devs") == ["groupadd", "devs"]
    assert c.groupdel_argv("devs") == ["groupdel", "devs"]


@pytest.mark.parametrize("bad", ["Alice", "0bad", "a;rm -rf /", "root\n", "al ice", ""])
def test_rejects_bad_names(bad):
    with pytest.raises(ValueError):
        c.useradd_argv(bad)


def test_rejects_injection_in_fields():
    with pytest.raises(ValueError):
        c.useradd_argv("alice", shell="not-a-path")
    with pytest.raises(ValueError):
        c.useradd_argv("alice", comment="a:b")  # colon would corrupt passwd
    with pytest.raises(ValueError):
        c.useradd_argv("alice", groups="wheel,Bad Name")


def test_chpasswd_input_feeds_stdin_not_argv():
    argv, stdin = c.chpasswd_input("alice", "s3cret:with:colons")
    assert argv == ["chpasswd"]
    assert stdin == "alice:s3cret:with:colons\n"  # colons ok; whole thing on stdin


@pytest.mark.parametrize("pw", ["", "has\nnewline", "cr\rreturn"])
def test_chpasswd_rejects_bad_passwords(pw):
    with pytest.raises(ValueError):
        c.chpasswd_input("alice", pw)


def test_gpasswd_argv_add_and_remove():
    assert c.gpasswd_argv("wheel", "alice", add=True) == ["gpasswd", "-a", "alice", "wheel"]
    assert c.gpasswd_argv("wheel", "alice", add=False) == ["gpasswd", "-d", "alice", "wheel"]
    with pytest.raises(ValueError):
        c.gpasswd_argv("wheel", "Bad User", add=True)
