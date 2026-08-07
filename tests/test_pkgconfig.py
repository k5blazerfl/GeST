"""Tests for the keyword/mask model (package.accept_keywords / mask / unmask)."""

from gest.core.software import pkgconfig as pc


def test_keyword_line_building():
    assert pc.keyword_line("cat/pkg", pc.KW_DEFAULT) == ""
    assert pc.keyword_line("cat/pkg", pc.KW_TESTING) == f"cat/pkg ~{pc.arch()}"
    assert pc.keyword_line("cat/pkg", pc.KW_ANY) == "cat/pkg **"


def test_read_line_and_states(monkeypatch, tmp_path):
    (tmp_path / "accept_keywords").write_text("cat/pkg **\ncat/other ~amd64\n")
    (tmp_path / "mask").write_text("cat/pkg\n")
    monkeypatch.setattr(pc, "gest_path", lambda kind: str(tmp_path / kind))
    assert pc.keyword_state("cat/pkg") == pc.KW_ANY
    assert pc.keyword_state("cat/other") == pc.KW_TESTING
    assert pc.keyword_state("cat/none") == pc.KW_DEFAULT
    assert pc.mask_state("cat/pkg") == pc.MASKED
    assert pc.mask_state("cat/none") == pc.MASK_DEFAULT


def test_changed_writes_only_reports_diffs(monkeypatch, tmp_path):
    for kind in ("accept_keywords", "mask", "unmask"):
        (tmp_path / kind).write_text("")
    monkeypatch.setattr(pc, "gest_path", lambda kind: str(tmp_path / kind))
    writes = dict(pc.changed_writes("cat/pkg", pc.KW_TESTING, pc.MASKED))
    assert writes["accept_keywords"] == f"cat/pkg ~{pc.arch()}"
    assert writes["mask"] == "cat/pkg"
    assert "unmask" not in writes  # unchanged (stays empty)
    assert pc.changed_writes("cat/pkg", pc.KW_DEFAULT, pc.MASK_DEFAULT) == []
