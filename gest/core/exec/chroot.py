"""A chroot view of an `Executor`: run the same argv *inside* the target root.

This is the seam that lets every module apply function stay agnostic about
whether it runs on the live CD's host or inside the install target. A
:class:`ChrootExecutor` wraps an inner `Executor` and rewrites each call from
``argv`` to ``["chroot", root, *argv]`` — nothing else changes, so `run_steps`
and the module pipelines (sync, profile, ``@world`` merge, kernel build,
``grub-mkconfig``, root password) compose unchanged over the target.

`chroot` requires uid 0, which is exactly the `DirectExecutor` precondition, so
this only ever sits over the direct/live-CD path — there is no D-Bus surface. The
root is guarded at construction with the same target-root confinement the disk
module uses (`mount.guard_target_root`), so a `ChrootExecutor` can never wrap the
running system (``/`` is refused).
"""

from __future__ import annotations

from gest.core.disk import mount
from gest.core.exec.executor import Executor
from gest.core.exec.runner import OnProgress, RunResult


class ChrootExecutor:
    """Run commands inside ``root`` by delegating ``chroot root <argv>`` to ``inner``.

    ``root`` is confined to the ``/mnt`` / ``/media`` / ``/run/media`` prefixes at
    construction (via :func:`gest.core.disk.mount.guard_target_root`), so it can
    never target ``/`` — the running system.
    """

    def __init__(self, inner: Executor, root: str) -> None:
        mount.guard_target_root(root)
        self._inner = inner
        self._root = root

    @property
    def root(self) -> str:
        """The target root every command is chrooted into."""
        return self._root

    async def run(
        self, argv: list[str], *, on_progress: OnProgress | None = None
    ) -> RunResult:
        """Run ``argv`` inside the target: ``inner.run(["chroot", root, *argv])``."""
        return await self._inner.run(["chroot", self._root, *argv], on_progress=on_progress)
