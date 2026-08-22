"""The TUI kernel-console quiet-down (gest/tui/console.py). No real /proc — the
printk path is redirected to a temp file and the VT check is forced."""

from __future__ import annotations

from gest.tui import console


def _level(path) -> str:
    return path.read_text().split()[0]


def test_quiets_then_restores_on_a_vt(tmp_path, monkeypatch):
    printk = tmp_path / "printk"
    printk.write_text("4\t4\t1\t7\n")                 # kernel default-ish
    monkeypatch.setattr(console, "_PRINTK", str(printk))
    monkeypatch.setattr(console, "_on_vt", lambda: True)

    with console.quiet_kernel_console():
        assert _level(printk) == "1"                  # quieted while the TUI is up
    assert _level(printk) == "4"                      # prior level restored on exit


def test_restores_even_when_body_raises(tmp_path, monkeypatch):
    printk = tmp_path / "printk"
    printk.write_text("7 4 1 7\n")
    monkeypatch.setattr(console, "_PRINTK", str(printk))
    monkeypatch.setattr(console, "_on_vt", lambda: True)

    try:
        with console.quiet_kernel_console():
            assert _level(printk) == "1"
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert _level(printk) == "7"                       # still restored


def test_noop_off_a_vt(tmp_path, monkeypatch):
    printk = tmp_path / "printk"
    printk.write_text("4 4 1 7\n")
    monkeypatch.setattr(console, "_PRINTK", str(printk))
    monkeypatch.setattr(console, "_on_vt", lambda: False)

    with console.quiet_kernel_console():
        assert _level(printk) == "4"                   # untouched on a pty/SSH
    assert _level(printk) == "4"


def test_noop_when_printk_unwritable(monkeypatch):
    # Missing/again unwritable path must not raise — just silently do nothing.
    monkeypatch.setattr(console, "_PRINTK", "/nonexistent/printk")
    monkeypatch.setattr(console, "_on_vt", lambda: True)
    with console.quiet_kernel_console():
        pass
