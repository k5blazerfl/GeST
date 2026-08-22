"""``run_install`` — the loop that runs an ordered list of install steps.

Deliberately thin (docs/design/installer-flow-engine.md §5): run the steps in
order, skip any that are already satisfied, pick the host-or-chroot executor per
step (the step does that itself), stream progress, and — once a step has opened
the pseudo-filesystems — always tear them down in a ``finally`` via the
never-raising :func:`teardown_chroot`, so a partial install leaves a cleanly
unmountable target. Writes are not rolled back; that is what makes resume
possible.

On a step failure the loop consults the optional ``on_failure`` hook for an
in-run decision — :class:`FailureAction`. ``RETRY`` re-runs the same step (it was
never marked done, so the retry is clean); ``SKIP`` marks it satisfied and moves
on (loud, dangerous — the UI names the risk); ``ABORT`` re-raises. With no hook
the first failure propagates, exactly as before (docs/design/installer-boot-
modernization.md, Phase 1).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import Enum

from gest.core.chroot.prepare import teardown_chroot
from gest.core.exec.runner import OnProgress
from gest.core.install.context import InstallContext
from gest.core.install.step import InstallStep


class FailureAction(Enum):
    """What to do about a step that just failed (returned by ``on_failure``)."""

    RETRY = "retry"      # run the same step again
    SKIP = "skip"        # mark it done and continue (dangerous)
    ABORT = "abort"      # re-raise; stop the run


# Called with the failed step, the exception it raised, and whether the target
# chroot's pseudo-filesystems are currently mounted (so the UI can offer a shell
# *inside* the target vs. on the live host). Returns the chosen action.
OnFailure = Callable[[InstallStep, Exception, bool], Awaitable[FailureAction]]


async def run_install(
    ctx: InstallContext,
    steps: list[InstallStep],
    *,
    on_progress: OnProgress | None = None,
    on_step: Callable[[int], None] | None = None,
    on_failure: OnFailure | None = None,
) -> None:
    """Run ``steps`` in order against ``ctx``.

    ``on_step`` is called with each step's index as it starts (already-satisfied
    steps are skipped, not reported as started). ``on_progress`` receives streamed
    output lines. Without ``on_failure`` the first step that raises propagates out
    — no later step runs — but the pseudo-filesystem teardown still runs. With
    ``on_failure`` the loop offers retry/skip/abort per :class:`FailureAction`.
    """
    opened_chroot = False
    try:
        index = 0
        while index < len(steps):
            step = steps[index]
            if await step.is_satisfied(ctx):
                if on_progress is not None:
                    on_progress([f"✓ {step.label} (already done)"])
                index += 1
                continue
            if on_step is not None:
                on_step(index)
            try:
                await step.run(ctx, on_progress)          # raises on failure
            except Exception as exc:
                if on_failure is None:
                    raise
                action = await on_failure(step, exc, opened_chroot)
                if action is FailureAction.RETRY:
                    continue                               # same index, don't advance
                if action is FailureAction.SKIP:
                    if on_progress is not None:
                        on_progress([f"⚠ skipped {step.label} after failure "
                                     "(the installed system may be incomplete)"])
                    ctx.state.mark(step)
                    index += 1
                    continue
                raise                                      # ABORT
            if getattr(step, "opens_chroot", False):
                opened_chroot = True
            ctx.state.mark(step)
            index += 1
    finally:
        if opened_chroot:
            await teardown_chroot(ctx.root, ctx.host, on_progress=on_progress)
