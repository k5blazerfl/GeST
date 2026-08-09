"""List log sources and read them (tail), unprivileged and read-only."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable

from gest.core.logs.model import LogSource

Runner = Callable[[list[str]], str]

VAR_LOG = "/var/log"
DEFAULT_MAX_LINES = 2000

_DMESG = LogSource("dmesg", "dmesg (kernel ring buffer)", "command")
_RCLOG = LogSource("rc.log", "OpenRC boot log", "file", "/var/log/rc.log")

# Well-known logs to surface first (filename → label), if present and readable.
_KNOWN = [
    ("messages", "System messages"),
    ("syslog", "Syslog"),
    ("dmesg", "Saved dmesg (last boot)"),
    ("emerge.log", "Portage: emerge"),
    ("emerge-fetch.log", "Portage: fetch"),
    ("Xorg.0.log", "Xorg"),
]


def _readable_file(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.R_OK)


def list_sources(var_log: str = VAR_LOG) -> list[LogSource]:
    """Available log sources: dmesg, the boot log, then readable /var/log files."""
    sources: list[LogSource] = [_DMESG]
    seen: set[str] = set()
    if _readable_file(_RCLOG.path):
        sources.append(_RCLOG)
        seen.add(_RCLOG.path)
    for name, label in _KNOWN:
        path = os.path.join(var_log, name)
        if path not in seen and _readable_file(path):
            sources.append(LogSource(name, label, "file", path))
            seen.add(path)
    try:
        entries = sorted(os.listdir(var_log))
    except OSError:
        entries = []
    for name in entries:
        path = os.path.join(var_log, name)
        if path not in seen and _readable_file(path):
            sources.append(LogSource(name, name, "file", path))
            seen.add(path)
    return sources


def _read_dmesg(runner: Runner | None) -> list[str]:
    if runner is not None:
        return runner(["dmesg"]).splitlines() or ["(no output)"]
    try:
        proc = subprocess.run(["dmesg"], capture_output=True, text=True)
    except OSError as exc:
        return [f"(dmesg unavailable: {exc})"]
    if proc.returncode != 0 or not proc.stdout.strip():
        why = proc.stderr.strip() or "no output"
        return [f"(dmesg failed: {why} — kernel.dmesg_restrict may require root; "
                f"try the saved /var/log/dmesg file instead)"]
    return proc.stdout.splitlines()


def read_source(
    source: LogSource, *, max_lines: int = DEFAULT_MAX_LINES, runner: Runner | None = None
) -> list[str]:
    """Return the last ``max_lines`` lines of a source (raw, may contain ANSI)."""
    if source.kind == "command":
        lines = _read_dmesg(runner)
    else:
        try:
            with open(source.path, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError as exc:
            return [f"(cannot read {source.path}: {exc})"]
    return lines[-max_lines:] if len(lines) > max_lines else lines
