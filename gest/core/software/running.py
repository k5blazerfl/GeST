"""Detect an *external* Portage operation — an emerge/emaint/ebuild running in a
terminal, outside GeST.

GeST already serializes its own package operations through the single root
backend (the cross-session lock). This closes the other gap: a merge or sync a
user started by hand in a shell. Starting a second Portage operation on top of it
would collide on Portage's own locks and fail uglily, so the backend consults
this before starting (or reporting) an operation.

It is a deliberately conservative process scan: a *read-only* emerge
(``--pretend`` / ``--search`` / ``--info``) is ignored so leaving ``emerge -pv``
open in a shell doesn't lock GeST out — only an actually-mutating run counts.
"""

from __future__ import annotations

import os

# Portage entry points that mutate state (a build/merge, a tree/repo sync, or a
# manual ebuild phase). The main ``emerge`` process stays alive for the whole
# run, so scanning for it catches a merge throughout, not just at its edges.
_MUTATING = {"emerge", "emaint", "ebuild"}

# Long options that make an ``emerge`` invocation read-only — safe to ignore.
_READONLY_LONG = {
    "--pretend", "--search", "--searchdesc", "--info",
    "--help", "--version", "--check-news",
}


def _command_of(args: list[str]) -> str:
    """The command a process is running, seeing through the python-exec wrapper.

    emerge/emaint are python scripts, so argv[0] is often the interpreter with
    the script as argv[1]; unwrap that. Reading argv[0] (not any argument) avoids
    matching e.g. ``vim emerge`` or ``grep emerge``.
    """
    a0 = os.path.basename(args[0])
    if a0.startswith("python") and len(args) > 1:
        return os.path.basename(args[1])
    return a0


def _emerge_is_readonly(args: list[str]) -> bool:
    """True when an ``emerge`` invocation only queries (never mutates)."""
    for a in args:
        if a in _READONLY_LONG:
            return True
        # A short-option cluster containing p (pretend) or s/S (search).
        if len(a) > 1 and a[0] == "-" and a[1] != "-" and any(
                c in a[1:] for c in "psS"):
            return True
    return False


def external_emerge(proc_root: str = "/proc") -> str | None:
    """Return the command of a mutating external Portage run (``"emerge"`` /
    ``"emaint"`` / ``"ebuild"``), or ``None`` if none is running.

    ``proc_root`` is injectable for testing. Any read/scan error is treated as
    "nothing running" — this is an advisory safety check, never a hard gate on
    GeST being usable.
    """
    try:
        pids = os.listdir(proc_root)
    except OSError:
        return None
    for pid in pids:
        if not pid.isdigit():
            continue
        try:
            with open(os.path.join(proc_root, pid, "cmdline"), "rb") as fh:
                raw = fh.read()
        except OSError:
            continue                      # process vanished / not readable
        args = [t.decode("utf-8", "replace") for t in raw.split(b"\x00") if t]
        if not args:
            continue
        command = _command_of(args)
        if command not in _MUTATING:
            continue
        if command == "emerge" and _emerge_is_readonly(args):
            continue                      # emerge -pv / --search etc. — ignore
        return command
    return None
