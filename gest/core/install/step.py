"""The ``InstallStep`` protocol and its two base classes.

A step is a labelled unit that knows its phase, whether it runs inside the target
(``chroot``) or writes under the root via the seam (``target_aware``), how to
``run`` (raising on failure), and whether it ``is_satisfied`` already (so a re-run
can skip it). It picks the host-or-chroot executor itself from the context, so the
engine loop stays trivial. ``opens_chroot`` marks the one step that mounts the
pseudo-filesystems, so the engine knows to tear them down afterwards.

Most registry entries are one of two bases:

- ``ArgvStep`` — a pure-argv operation (or sub-pipeline). Subclass sets the markers
  and implements ``build(ctx) -> list[Step]``; ``run`` sends them through
  ``run_steps`` on the selected executor, so an in-chroot step becomes
  ``["chroot", root, ...]`` with no extra code.
- ``FuncStep`` — a richer step that is not a single argv (stage3 unpack, a config
  render+write); subclass overrides ``run`` directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from gest.core.exec.runner import OnProgress
from gest.core.exec.steps import Step, run_steps

if TYPE_CHECKING:
    from gest.core.install.context import InstallContext
    from gest.core.install.plan import Phase


@runtime_checkable
class InstallStep(Protocol):
    """One unit of an install. See the module docstring for the field meanings."""

    label: str
    phase: Phase
    chroot: bool
    target_aware: bool
    opens_chroot: bool

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        """Perform the step; raise (StepError/DiskApplyError/ValueError) on failure."""
        ...

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        """True if a re-run may skip this step (already done)."""
        ...


class _BaseStep:
    """Shared defaults for the concrete step bases."""

    label: str = ""
    phase: Phase
    chroot: bool = False
    target_aware: bool = False
    opens_chroot: bool = False

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return False


class ArgvStep(_BaseStep):
    """A step that runs one or more argv ``Step``s through the selected executor."""

    def build(self, ctx: InstallContext) -> list[Step]:
        """Return the ordered argv steps to run. Subclasses implement this."""
        raise NotImplementedError

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        executor = ctx.executor_for(self.chroot)
        await run_steps(self.build(ctx), executor, on_progress=on_progress)


class FuncStep(_BaseStep):
    """A step with a richer async body; subclasses override ``run``."""

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        raise NotImplementedError
