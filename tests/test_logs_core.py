"""CI-safe tests for the system logs core (source listing + tail reading)."""

from gest.core.logs import reader
from gest.core.logs.model import LogSource


def test_list_sources_readable_files_only(tmp_path):
    (tmp_path / "messages").write_text("a\nb\n")
    (tmp_path / "custom.log").write_text("x\n")
    (tmp_path / "portage").mkdir()  # a directory — must be skipped
    keys = [s.key for s in reader.list_sources(str(tmp_path))]
    assert keys[0] == "dmesg"                     # the command source is always first
    assert "messages" in keys and "custom.log" in keys
    assert "portage" not in keys                  # directory excluded
    assert keys.index("messages") < keys.index("custom.log")  # known ones first


def test_read_source_tails_file(tmp_path):
    f = tmp_path / "big.log"
    f.write_text("\n".join(str(i) for i in range(100)) + "\n")
    lines = reader.read_source(LogSource("big", "big", "file", str(f)), max_lines=10)
    assert lines == [str(i) for i in range(90, 100)]


def test_read_source_missing_file_returns_note(tmp_path):
    out = reader.read_source(LogSource("x", "x", "file", str(tmp_path / "nope")))
    assert len(out) == 1 and "cannot read" in out[0]


def test_read_dmesg_via_injected_runner():
    out = reader.read_source(LogSource("dmesg", "dmesg", "command"),
                             runner=lambda argv: "line1\nline2")
    assert out == ["line1", "line2"]
