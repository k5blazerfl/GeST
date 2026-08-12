"""The shared subprocess runner: run argv, stream output, return an exit result.

This is the one place that actually launches a tool and turns its output into the
line-batch stream the TUI consumes (`runscreen.py`). Both `DirectExecutor` (which
calls it in-process) and — in a later step — the root backend delegate here, so
the streaming and exit-handling behaviour is identical on the live CD and on an
installed system. No D-Bus and no polkit live here; this is pure execution.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

OnProgress = Callable[[list[str]], None]


@dataclass(slots=True)
class RunResult:
    """The outcome of one command: its exit code and captured output."""

    code: int
    output: str


async def stream(argv: list[str], on_progress: OnProgress | None = None) -> RunResult:
    """Run ``argv``, forwarding each output line to ``on_progress`` as it arrives.

    stdout and stderr are merged (the order the user would see in a terminal).
    Each line is delivered as a one-element batch — callers that coalesce can
    buffer; the batch shape matches the backend's ``Progress`` signal so the two
    executors are interchangeable. Returns a :class:`RunResult`.
    """
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    lines: list[str] = []
    assert proc.stdout is not None
    async for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").rstrip("\n")
        lines.append(line)
        if on_progress is not None:
            on_progress([line])
    await proc.wait()
    return RunResult(proc.returncode or 0, "\n".join(lines))
