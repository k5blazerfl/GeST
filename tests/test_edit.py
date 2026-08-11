"""Tests for the repos.conf section rewrite behind repo Edit and the mirror picker."""

from gest.core.repos import edit


def test_set_fields_replaces_and_inserts_preserving_rest():
    text = (
        "[guru]\n"
        "location = /var/db/repos/guru\n"
        "sync-type = git\n"
        "sync-uri = https://old/guru.git\n"
        "auto-sync = yes\n"
    )
    out = edit.set_fields(text, "guru",
                          {"sync-type": "git", "sync-uri": "https://new/guru.git",
                           "priority": "70"})
    assert "sync-uri = https://new/guru.git" in out
    assert "https://old" not in out
    assert "priority = 70" in out                      # inserted (was absent)
    assert "location = /var/db/repos/guru" in out      # preserved
    assert "auto-sync = yes" in out


def test_set_fields_empty_value_deletes_key():
    text = "[guru]\nsync-uri = https://h/guru.git\npriority = 50\n"
    out = edit.set_fields(text, "guru", {"priority": ""})
    assert "priority" not in out
    assert "sync-uri = https://h/guru.git" in out


def test_set_fields_creates_override_when_absent():
    out = edit.set_fields("", "guru",
                          {"sync-type": "git", "sync-uri": "https://h/guru.git"})
    assert out == "[guru]\nsync-type = git\nsync-uri = https://h/guru.git\n"


def test_set_fields_only_touches_named_section():
    text = ("[guru]\nsync-uri = https://old/guru.git\n"
            "[other]\nsync-uri = https://other/thing\n")
    out = edit.set_fields(text, "guru", {"sync-uri": "https://new/guru.git"})
    assert "https://new/guru.git" in out
    assert "https://other/thing" in out                # other section untouched
    assert "https://old/guru.git" not in out


def test_locate_finds_defining_fragment(tmp_path):
    (tmp_path / "a.conf").write_text("[foo]\nlocation = /x\n")
    (tmp_path / "b.conf").write_text("[guru]\nsync-uri = https://h/guru.git\n")
    path, text = edit.locate(str(tmp_path), "guru")
    assert path.endswith("b.conf") and "guru" in text


def test_locate_returns_new_path_for_unknown_repo(tmp_path):
    path, text = edit.locate(str(tmp_path), "newrepo")
    assert path.endswith("newrepo.conf") and text == ""
