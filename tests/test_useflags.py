"""Tests for the USE-flag model: line building, file merge, override parsing."""

from gest.core.software import useflags as uf


def test_build_line_tristate():
    line = uf.build_line("cat/pkg", {"a": uf.ON, "b": uf.OFF, "c": uf.DEFAULT})
    assert line == "cat/pkg a -b"  # sorted flags; default flag omitted


def test_build_line_all_default_is_empty():
    assert uf.build_line("cat/pkg", {"a": uf.DEFAULT, "b": uf.DEFAULT}) == ""


def test_render_file_replaces_only_target(monkeypatch, tmp_path):
    f = tmp_path / "gest"
    f.write_text("cat/one x -y\ncat/two z\n# a comment\n")
    monkeypatch.setattr(uf, "gest_file", lambda: str(f))
    new = uf.render_file("cat/one", "cat/one a")
    lines = new.strip().splitlines()
    assert "cat/two z" in lines
    assert "# a comment" in lines
    assert "cat/one a" in lines
    assert "cat/one x -y" not in lines


def test_render_file_removes_entry_when_empty(monkeypatch, tmp_path):
    f = tmp_path / "gest"
    f.write_text("cat/one x\ncat/two z\n")
    monkeypatch.setattr(uf, "gest_file", lambda: str(f))
    new = uf.render_file("cat/one", "")
    assert "cat/one" not in new
    assert "cat/two z" in new


def test_read_overrides_parses_tristate(monkeypatch, tmp_path):
    f = tmp_path / "gest"
    f.write_text("# header\ncat/pkg a -b\n")
    monkeypatch.setattr(uf, "gest_file", lambda: str(f))
    assert uf.read_overrides() == {"cat/pkg": {"a": True, "b": False}}
