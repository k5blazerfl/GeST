"""The `Executor` interface and its implementations.

`Executor` is the seam the rest of `core` depends on instead of D-Bus: an async
``run(argv)`` that streams output and returns a `RunResult`. Three implementations:

* `DirectExecutor` — runs the tool in-process via `runner.stream`. Selected only
  when already root (live CD / root shell), where the polkit gate is vacuous.
* `DBusExecutor` — marshals to the root backend over the system bus. This is the
  installed-system path; it is a thin adapter over the per-module backend clients
  that already exist (`gest/core/*/backend_client.py`). Left as a stub here — the
  scaffolding wires the direct path first, since that's what the partitioner is
  tested on; the D-Bus adapter lands with the backend `Disk` methods.
* `FakeExecutor` — records the argv it was asked to run and replays canned exit
  codes, so pipeline/ordering logic is tested with no subprocess and no bus.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from gest.core.exec.runner import OnProgress, RunResult, stream


class Executor(Protocol):
    """Runs one command and streams its output. The core depends on this, not D-Bus.

    ``stdin`` feeds a small text payload to the tool (e.g. the ``name:password``
    line ``chpasswd`` reads); it is keyword-only and defaults to ``None``.
    """

    async def run(self, argv: list[str], *, on_progress: OnProgress | None = None,
                  stdin: str | None = None) -> RunResult:
        ...


class DirectExecutor:
    """Run tools in-process. Only valid when the process is already uid 0."""

    async def run(self, argv: list[str], *, on_progress: OnProgress | None = None,
                  stdin: str | None = None) -> RunResult:
        return await stream(argv, on_progress, stdin=stdin)


class DBusExecutor:
    """Marshal to the root backend over the system bus (installed-system path).

    Stub: the concrete adapter forwards to the module's ``backend_client`` and
    maps ``BUSY_ERROR`` to ``BackendBusy`` (as ``core/software/backend_client``
    already does). It is filled in alongside the backend ``Disk`` provisioning
    methods; until then, selecting it raises so a misconfigured runtime fails
    loudly rather than silently no-opping.
    """

    async def run(self, argv: list[str], *, on_progress: OnProgress | None = None,
                  stdin: str | None = None) -> RunResult:
        raise NotImplementedError(
            "DBusExecutor is not yet wired; run GeST as root for the direct path"
        )


class FakeExecutor:
    """Test double: records calls and returns codes from ``code_for(argv)``.

    ``calls`` holds the argv of each run; ``stdins`` is the parallel list of the
    ``stdin`` each run was given (``None`` when none), so a test can assert a
    secret was piped without it appearing in ``calls``.
    """

    def __init__(self, code_for: Callable[[list[str]], int] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.stdins: list[str | None] = []
        self._code_for = code_for or (lambda _argv: 0)

    async def run(self, argv: list[str], *, on_progress: OnProgress | None = None,
                  stdin: str | None = None) -> RunResult:
        self.calls.append(list(argv))
        self.stdins.append(stdin)
        if on_progress is not None:
            on_progress(["$ " + " ".join(argv)])
        return RunResult(self._code_for(argv), "")
