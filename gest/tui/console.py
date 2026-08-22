"""Quiet the kernel console while a full-screen TUI owns the terminal.

On a text console the kernel prints messages (printk) straight to the
foreground VT, painting right over the urwid display — most visibly on the
installer ISO, which boots verbose (``loglevel=4``) and autostarts the wizard
on tty1. While our TUI is up we lower the *console* loglevel so only the
severest messages (oops/panic) can still break through, and we restore the
previous level on exit. Nothing is lost: every message stays in the kernel ring
buffer (``dmesg``) and, on the installer ISO, is streamed live to tty12
(Alt+F12) by journald's ForwardToConsole.

All of this is best-effort and self-restoring: it only acts on a real Linux VT
and only when we can write ``/proc/sys/kernel/printk`` (i.e. as root, which the
installer is). Anywhere else — a pty, an SSH session, an unprivileged desktop
terminal — it is a silent no-op.
"""

from __future__ import annotations

import contextlib
import os
import sys

_PRINTK = "/proc/sys/kernel/printk"
# console_loglevel 1 (KERN_ALERT and above): panics/oopses still surface, but the
# ERR/WARNING/NOTICE/INFO chatter that scribbles over the UI does not.
_QUIET = 1


def _on_vt() -> bool:
    """True only when stdout is a real Linux virtual terminal (``/dev/ttyN`` or a
    serial console), not a pty/SSH — the only place printk paints the screen."""
    try:
        return os.isatty(sys.stdout.fileno()) and os.ttyname(
            sys.stdout.fileno()
        ).startswith("/dev/tty")
    except OSError:
        return False


@contextlib.contextmanager
def quiet_kernel_console(level: int = _QUIET):
    """Lower the console loglevel for the duration, restoring it afterwards.

    A no-op (still a valid context manager) when not on a VT or when
    ``/proc/sys/kernel/printk`` isn't writable, so callers can wrap
    unconditionally.
    """
    prev: str | None = None
    if _on_vt():
        with contextlib.suppress(OSError):
            with open(_PRINTK) as fh:
                prev = fh.read().split()[0]          # current console_loglevel
            with open(_PRINTK, "w") as fh:
                fh.write(f"{level}\n")
    try:
        yield
    finally:
        if prev is not None:
            with contextlib.suppress(OSError), open(_PRINTK, "w") as fh:
                fh.write(f"{prev}\n")
