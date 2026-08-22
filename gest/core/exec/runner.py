"""The shared subprocess runner: run argv, stream output, return an exit result.

This is the one place that actually launches a tool and turns its output into the
line-batch stream the TUI consumes (`runscreen.py`). Both `DirectExecutor` (which
calls it in-process) and — in a later step — the root backend delegate here, so
the streaming and exit-handling behaviour is identical on the live CD and on an
installed system. No D-Bus and no polkit live here; this is pure execution.
"""

from __future__ import annotations

import asyncio
import errno as _errno
from collections.abc import Callable
from dataclasses import dataclass

OnProgress = Callable[[list[str]], None]

# Exit code used when a command can't be launched at all (exec failed) — the
# shell convention for "command not found / not executable".
EXEC_FAILED = 127


@dataclass(slots=True)
class RunResult:
    """The outcome of one command: its exit code and captured output."""

    code: int
    output: str


async def stream(
    argv: list[str], on_progress: OnProgress | None = None, *, stdin: str | None = None
) -> RunResult:
    """Run ``argv``, forwarding each output line to ``on_progress`` as it arrives.

    stdout and stderr are merged (the order the user would see in a terminal).
    Each line is delivered as a one-element batch — callers that coalesce can
    buffer; the batch shape matches the backend's ``Progress`` signal so the two
    executors are interchangeable. Returns a :class:`RunResult`.

    ``stdin`` feeds a small text payload to the tool (e.g. ``chpasswd`` reading
    ``name:password``): it is written and the pipe closed before stdout is read.
    This is safe for the tiny inputs it is used for; it is not a general
    bidirectional stream.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        # The binary couldn't be launched at all. Most often ENOENT (missing) or —
        # on real hardware — EIO, a physical read error off a failing or
        # badly-burned install medium. Turn it into a normal non-zero result with
        # a legible message rather than letting a raw OSError abort the whole run,
        # so pipelines report WHICH command failed and WHY (and can fall back).
        why = f"{exc.strerror or exc} (errno {exc.errno})"
        if exc.errno == _errno.EIO:
            why += (" — the install medium may be failing; verify the ISO checksum "
                    "and re-burn to another USB")
        msg = f"could not run {argv[0]!r}: {why}"
        if on_progress is not None:
            on_progress([msg])
        return RunResult(EXEC_FAILED, msg)
    if stdin is not None and proc.stdin is not None:
        proc.stdin.write(stdin.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()
    lines: list[str] = []
    assert proc.stdout is not None
    async for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").rstrip("\n")
        lines.append(line)
        if on_progress is not None:
            on_progress([line])
    await proc.wait()
    return RunResult(proc.returncode or 0, "\n".join(lines))
