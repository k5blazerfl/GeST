"""Tests for the core Portage-config write builders (USE flags, keyword/mask).

These replace the old backend package.use writer: the frontend now renders the
full new file contents into a :class:`~gest.core.portage.write.ConfigWrite`,
applied by the Portage ``WriteConfig`` RPC. The merge/replace/remove semantics
themselves live in the shared ``atomfile`` codec (see ``test_portage_core.py``);
here we check the builders wire cp / line / path together correctly.
"""

from gest.core.software import pkgconfig as pc
from gest.core.software import useflags as uf


def test_useflags_write_for_replaces_target_keeps_others(monkeypatch, tmp_path):
    f = tmp_path / "gest"
    f.write_text("cat/two z\ncat/one old\n# note\n")
    monkeypatch.setattr(uf, "gest_file", lambda: str(f))
    cw = uf.write_for("cat/one", {"a": uf.ON, "b": uf.OFF})
    assert cw.path == str(f)
    assert "cat/one a -b" in cw.text          # sorted flags; on/off tokens
    assert "cat/one old" not in cw.text        # old line dropped
    assert "cat/two z" in cw.text and "# note" in cw.text  # siblings/comments kept


def test_useflags_write_for_all_default_removes_entry(monkeypatch, tmp_path):
    f = tmp_path / "gest"
    f.write_text("cat/one a\ncat/two z\n")
    monkeypatch.setattr(uf, "gest_file", lambda: str(f))
    cw = uf.write_for("cat/one", {"a": uf.DEFAULT})   # all-default → empty line
    assert "cat/one" not in cw.text
    assert "cat/two z" in cw.text


def test_pkgconfig_writes_for_one_configwrite_per_changed_kind(monkeypatch, tmp_path):
    for kind in ("accept_keywords", "mask", "unmask"):
        (tmp_path / kind).write_text("")
    monkeypatch.setattr(pc, "gest_path", lambda kind: str(tmp_path / kind))
    writes = pc.writes_for("cat/pkg", pc.KW_TESTING, pc.MASKED)
    by_path = {w.path: w.text for w in writes}
    assert f"cat/pkg ~{pc.arch()}" in by_path[str(tmp_path / "accept_keywords")]
    assert by_path[str(tmp_path / "mask")].split("\n")[0] == "cat/pkg"
    # unmask is unchanged (stays empty) → no ConfigWrite emitted for it
    assert str(tmp_path / "unmask") not in by_path


def test_pkgconfig_writes_for_noop_when_unchanged(monkeypatch, tmp_path):
    for kind in ("accept_keywords", "mask", "unmask"):
        (tmp_path / kind).write_text("")
    monkeypatch.setattr(pc, "gest_path", lambda kind: str(tmp_path / kind))
    assert pc.writes_for("cat/pkg", pc.KW_DEFAULT, pc.MASK_DEFAULT) == []
