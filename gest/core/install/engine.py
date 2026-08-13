"""``run_install`` — the loop that runs an ordered list of install steps.

Deliberately thin (docs/design/installer-flow-engine.md §5): run the steps in
order, skip any that are already satisfied, pick the host-or-chroot executor per
step (the step does that itself), stream progress, stop at the first failure, and
— once a step has opened the pseudo-filesystems — always tear them down in a
``finally`` via the never-raising :func:`teardown_chroot`, so a partial install
leaves a cleanly unmountable target. Writes are not rolled back; that is what makes
resume possible.
"""

from __future__ import annotations

from collections.abc import Callable

from gest.core.chroot.prepare import teardown_chroot
from gest.core.exec.runner import OnProgress
from gest.core.install.context import InstallContext
from gest.core.install.step import InstallStep


async def run_install(
    ctx: InstallContext,
    steps: list[InstallStep],
    *,
    on_progress: OnProgress | None = None,
    on_step: Callable[[int], None] | None = None,
) -> None:
    """Run ``steps`` in order against ``ctx``.

    ``on_step`` is called with each step's index as it starts (already-satisfied
    steps are skipped, not reported as started). The first step that raises
    propagates out — no later step runs — but the pseudo-filesystem teardown still
    runs. ``on_progress`` receives streamed output lines from each step.
    """
    opened_chroot = False
    try:
        for index, step in enumerate(steps):
            if await step.is_satisfied(ctx):
                if on_progress is not None:
                    on_progress([f"✓ {step.label} (already done)"])
                continue
            if on_step is not None:
                on_step(index)
            await step.run(ctx, on_progress)          # raises on failure
            if getattr(step, "opens_chroot", False):
                opened_chroot = True
            ctx.state.mark(step)
    finally:
        if opened_chroot:
            await teardown_chroot(ctx.root, ctx.host, on_progress=on_progress)
