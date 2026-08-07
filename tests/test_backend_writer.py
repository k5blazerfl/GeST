"""Tests for the backend's package.use writer (merge/replace/remove)."""

from gest.backend.service import SoftwareService


def test_writer_replaces_target_line_keeps_others(tmp_path):
    (tmp_path / "gest").write_text("cat/two z\ncat/one old\n")
    SoftwareService._write_package_use("cat/one", "cat/one a -b", directory=str(tmp_path))
    content = (tmp_path / "gest").read_text()
    assert "cat/one a -b" in content
    assert "cat/one old" not in content
    assert "cat/two z" in content


def test_writer_creates_then_removes(tmp_path):
    SoftwareService._write_package_use("cat/one", "cat/one a", directory=str(tmp_path))
    assert "cat/one a" in (tmp_path / "gest").read_text()
    SoftwareService._write_package_use("cat/one", "", directory=str(tmp_path))
    assert "cat/one" not in (tmp_path / "gest").read_text()


def test_config_writer_handles_generic_kinds(tmp_path):
    SoftwareService._write_package_config(
        "accept_keywords", "cat/pkg", "cat/pkg **", directory=str(tmp_path)
    )
    assert "cat/pkg **" in (tmp_path / "gest").read_text()
    SoftwareService._write_package_config(
        "mask", "cat/pkg", "cat/pkg", directory=str(tmp_path)
    )
    assert (tmp_path / "gest").read_text().strip() == "cat/pkg"
