"""Tests for the backend idle-exit decision and streamed-output batching."""

import sys

from gest.backend.service import SoftwareService


def test_should_exit_only_when_idle_and_no_active_ops():
    assert SoftwareService._should_exit(0, 130, 120) is True
    assert SoftwareService._should_exit(0, 119, 120) is False   # not idle enough
    assert SoftwareService._should_exit(1, 130, 120) is False   # merge streaming
    assert SoftwareService._should_exit(3, 999, 120) is False


def test_spawn_streaming_batches_output_without_loss():
    """A merge's output is coalesced into far fewer signals than lines, yet every
    line arrives in order and Finished carries the exit code."""
    import gi

    gi.require_version("GLib", "2.0")
    from gi.repository import GLib

    # A bare instance: _spawn_streaming only touches _active, _emit and _touch,
    # so we can drive it without a live D-Bus connection.
    svc = SoftwareService.__new__(SoftwareService)
    svc._active = 0
    svc._touch = lambda: None

    batches: list[list[str]] = []
    finished: list[int] = []
    loop = GLib.MainLoop()

    def fake_emit(signal, variant):
        if signal == "Progress":
            batches.append(variant.unpack()[0])
        elif signal == "Finished":
            finished.append(variant.unpack()[0])
            loop.quit()

    svc._emit = fake_emit

    n = 500
    svc._spawn_streaming(
        [sys.executable, "-c", f"[print(f'line {{i}}') for i in range({n})]"]
    )
    GLib.timeout_add_seconds(15, lambda: (loop.quit(), False)[1])  # safety net
    loop.run()

    lines = [ln for batch in batches for ln in batch]
    assert lines == [f"line {i}" for i in range(n)]  # complete and in order
    assert len(batches) < n                          # actually coalesced
    assert finished == [0]                            # clean exit reported
    assert svc._active == 0                           # streaming slot released


def test_spawn_streaming_detects_eof_with_blank_and_unterminated_lines():
    """EOF must be detected even though a blank line and a final unterminated
    line both look 'empty' — the case that made the old read_line loop spin."""
    import gi

    gi.require_version("GLib", "2.0")
    from gi.repository import GLib

    svc = SoftwareService.__new__(SoftwareService)
    svc._active = 0
    svc._touch = lambda: None

    lines: list[str] = []
    finished: list[int] = []
    loop = GLib.MainLoop()

    def fake_emit(signal, variant):
        if signal == "Progress":
            lines.extend(variant.unpack()[0])
        elif signal == "Finished":
            finished.append(variant.unpack()[0])
            loop.quit()

    svc._emit = fake_emit

    # 'a', then a blank line, then 'z' with NO trailing newline, exit code 3.
    svc._spawn_streaming(
        [sys.executable, "-c",
         "import sys; sys.stdout.write('a\\n\\nz'); sys.exit(3)"]
    )
    GLib.timeout_add_seconds(15, lambda: (loop.quit(), False)[1])  # safety net
    loop.run()

    assert lines == ["a", "", "z"]   # blank preserved; final unterminated kept
    assert finished == [3]           # loop actually reached EOF (didn't spin)
