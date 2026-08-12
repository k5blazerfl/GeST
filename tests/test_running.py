"""Unit tests for external-emerge detection (gest.core.software.running).

Builds a fake /proc tree of cmdlines so the scan is exercised without any real
processes. Pure and CI-friendly (no gi, no D-Bus).
"""

from gest.core.software.running import external_emerge


def _proc(tmp_path, procs):
    """Write {pid: [argv...]} as /proc-style cmdline files under tmp_path."""
    for pid, argv in procs.items():
        d = tmp_path / str(pid)
        d.mkdir()
        (d / "cmdline").write_bytes(b"\x00".join(a.encode() for a in argv) + b"\x00")
    # a non-pid entry and a pid with no cmdline, to exercise the skips
    (tmp_path / "self").mkdir()
    empty = tmp_path / "999"
    empty.mkdir()
    (empty / "cmdline").write_bytes(b"")
    return str(tmp_path)


def test_detects_a_running_merge(tmp_path):
    root = _proc(tmp_path, {101: ["/usr/bin/emerge", "-uDN", "@world"]})
    assert external_emerge(root) == "emerge"


def test_detects_emerge_via_python_exec_wrapper(tmp_path):
    root = _proc(tmp_path, {
        202: ["python3", "/usr/lib/python-exec/python3.13/emerge", "dev-vcs/git"]})
    assert external_emerge(root) == "emerge"


def test_ignores_readonly_pretend(tmp_path):
    root = _proc(tmp_path, {303: ["/usr/bin/emerge", "-pv", "@world"]})
    assert external_emerge(root) is None


def test_ignores_readonly_search_and_info(tmp_path):
    root = _proc(tmp_path, {
        304: ["/usr/bin/emerge", "--search", "vim"],
        305: ["/usr/bin/emerge", "--info"]})
    assert external_emerge(root) is None


def test_detects_emaint_sync(tmp_path):
    root = _proc(tmp_path, {404: ["/usr/sbin/emaint", "sync", "--repo", "guru"]})
    assert external_emerge(root) == "emaint"


def test_no_false_positive_from_an_argument_named_emerge(tmp_path):
    # editing/greping a file called "emerge" must not read as a running emerge
    root = _proc(tmp_path, {
        505: ["vim", "emerge"],
        506: ["grep", "-r", "emerge", "/etc"]})
    assert external_emerge(root) is None


def test_nothing_running(tmp_path):
    root = _proc(tmp_path, {707: ["/usr/bin/bash", "-i"]})
    assert external_emerge(root) is None


def test_missing_proc_root_is_safe():
    assert external_emerge("/nonexistent/proc/root") is None
