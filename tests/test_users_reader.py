"""Tests for the users/groups reader (pure parsing, CI-safe)."""

from gest.core.users import reader


def test_parse_passwd():
    text = (
        "# comment\n"
        "root:x:0:0:root:/root:/bin/bash\n"
        "alice:x:1000:1000:Alice Example,,,:/home/alice:/bin/zsh\n"
        "malformed-line-without-enough-fields\n"
    )
    users = reader.parse_passwd(text)
    by = {u.name: u for u in users}
    assert set(by) == {"root", "alice"}
    assert by["root"].uid == 0 and by["root"].system
    assert by["alice"].uid == 1000 and not by["alice"].system
    assert by["alice"].full_name == "Alice Example"
    assert by["alice"].shell == "/bin/zsh"


def test_parse_group():
    text = "wheel:x:10:root,alice\nusers:x:100:\nbad:line\n"
    groups = reader.parse_group(text)
    by = {g.name: g for g in groups}
    assert by["wheel"].gid == 10 and by["wheel"].members == ["root", "alice"]
    assert by["users"].members == []
    assert "bad" not in by
