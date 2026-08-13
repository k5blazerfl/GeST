"""The install runtime handle (``InstallContext``) and the completed-step store.

The context carries the already-decided runtime and the approved plan; steps read
it, they do not mutate the plan. The engine hands every step this one object and
lets the step pick its executor via :meth:`InstallContext.executor_for`.

``StateStore`` is the completed-step marker used for resume. This is the in-memory
core; persisting it (a ``/run`` session file before stage3, then the target's
``/etc/portage/gest/`` after) is a later sub-step — the engine only needs
``mark``/``done`` here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gest.core.exec.chroot import ChrootExecutor
from gest.core.exec.executor import Executor
from gest.core.install.plan import InstallPlan
from gest.core.install.step import InstallStep


class StateStore:
    """Records which steps have completed, so a re-run can skip them.

    A step is keyed by its ``key`` attribute if it has one, else its ``label``.
    In-memory only for now; a persistent backing lands with resume.
    """

    def __init__(self) -> None:
        self._done: set[str] = set()

    @staticmethod
    def _key(step: InstallStep) -> str:
        return getattr(step, "key", step.label)

    def mark(self, step: InstallStep) -> None:
        self._done.add(self._key(step))

    def done(self, key: str) -> bool:
        return key in self._done


@dataclass(slots=True)
class InstallContext:
    """The runtime handle threaded to every step.

    ``host`` is the process executor (``DirectExecutor`` on the live CD); ``target``
    is its :class:`ChrootExecutor` view of ``root`` for in-chroot steps. ``plan`` is
    optional so the engine mechanics can be exercised without a full plan; the real
    flow always sets it.
    """

    root: str
    host: Executor
    target: ChrootExecutor
    state: StateStore = field(default_factory=StateStore)
    plan: InstallPlan | None = None
    uuids: dict[str, str] = field(default_factory=dict)
    devices: list = field(default_factory=list)   # lsblk BlockDevices (Partition step)
    mounts: str = ""                              # /proc/mounts text (Partition step)

    def executor_for(self, chroot: bool) -> Executor:
        """The executor a step should run on: chroot view or the host."""
        return self.target if chroot else self.host
