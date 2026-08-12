"""A tiny ordered-pipeline primitive shared by provisioning modules.

A `Step` is a labelled argv; `run_steps` runs a list of them through an
`Executor`, streaming output and reporting each step's start (for progress UI),
and stops at the first non-zero exit with a `StepError`. Modules whose apply is
"run these commands in order on the direct/root path" (bootloader install, and
future kernel build) build on this instead of re-implementing the loop. (The disk
partitioner keeps its own richer pipeline because it also does pre-flight safety
validation.)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from gest.core.exec.executor import Executor
from gest.core.exec.runner import OnProgress, RunResult


@dataclass(slots=True, frozen=True)
class Step:
    """One command in a pipeline: a human label and the argv to run."""

    label: str
    argv: list[str]


class StepError(Exception):
    """A step exited non-zero; the pipeline stops at the first failure."""

    def __init__(self, step: Step, result: RunResult) -> None:
        self.step = step
        self.result = result
        super().__init__(f"{step.label} failed (exit {result.code})")


async def run_steps(
    steps: list[Step],
    executor: Executor,
    *,
    on_progress: OnProgress | None = None,
    on_step: Callable[[int], None] | None = None,
) -> list[Step]:
    """Run ``steps`` in order through ``executor``.

    ``on_step`` is called with each step's index as it starts. Raises
    :class:`StepError` at the first step that exits non-zero. Returns the steps on
    success.
    """
    for index, step in enumerate(steps):
        if on_step is not None:
            on_step(index)
        result = await executor.run(step.argv, on_progress=on_progress)
        if result.code != 0:
            raise StepError(step, result)
    return steps


def fail(label: str, output: str, code: int = 1) -> StepError:
    """Build a :class:`StepError` for a non-argv failure (e.g. a backend call)."""
    return StepError(Step(label, []), RunResult(code, output))
