"""The install runtime handle (``InstallContext``) and the completed-step store.

The context carries the already-decided runtime and the approved plan; steps read
it, they do not mutate the plan. The engine hands every step this one object and
lets the step pick its executor via :meth:`InstallContext.executor_for`.

``StateStore`` is the completed-step marker used for resume (design §6). With no
arguments it is a pure in-memory store (the engine only needs ``mark``/``done``);
bound to a target ``root`` it also persists to disk, in the two-phase location §6
prescribes — a ``/run`` session file before stage3, then the target's own
``/etc/portage/gest/`` state dir once stage3 has unpacked.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass, field

from gest.core import rootpath
from gest.core.exec.chroot import ChrootExecutor
from gest.core.exec.executor import Executor
from gest.core.install.plan import InstallPlan
from gest.core.install.step import InstallStep
from gest.core.portage import paths

#: The state file's basename, shared by both phases of its location (§6).
STATE_FILENAME = "install-state.json"
#: The live-session dir the state file lives in *before* stage3 (§6). The live CD
#: provides ``/run`` and a reboot discards it — correct, since nothing before
#: stage3 is resumable.
DEFAULT_RUN_DIR = "/run/gest"


class StateStore:
    """Records which steps have completed, so a re-run can skip them.

    A step is keyed by its ``key`` attribute if it has one, else its ``label``.

    ``StateStore()`` with no ``root`` is **in-memory only** — no file I/O — so the
    engine mechanics (and their tests) are unchanged. Passing a target ``root``
    turns on persistence: the completed set is loaded on construction and saved on
    every :meth:`mark`, to the two-phase location the design's §6 prescribes:

    * **before stage3** (the target's ``/etc`` does not exist yet) the file is
      ``<run_dir>/install-state.json`` — a live-session file discarded on reboot;
    * **once stage3 has unpacked** (``<root>/etc`` exists) the file is
      ``paths.gest_state("install-state.json", root)`` — the target's own
      GeST-private state dir, which survives a reboot so a post-stage3 install can
      be resumed. The first save that sees the target dir *migrates* any
      pre-stage3 ``<run_dir>`` marks into it (union), so nothing already done is
      re-run.

    The location is recomputed on every load/save, so a store constructed before
    stage3 seamlessly follows the marker across the boundary. ``run_dir`` and
    ``root`` are both injectable so tests never touch a real ``/run`` or ``/etc``.
    """

    def __init__(self, root: str | None = None, *, run_dir: str = DEFAULT_RUN_DIR) -> None:
        self._done: set[str] = set()
        self._root = root
        self._run_dir = run_dir
        if root is not None:
            self._load()

    @staticmethod
    def _key(step: InstallStep) -> str:
        return getattr(step, "key", step.label)

    def mark(self, step: InstallStep) -> None:
        self._done.add(self._key(step))
        if self._root is not None:
            self._save()

    def done(self, key: str) -> bool:
        return key in self._done

    # --- persistence (only active when bound to a target root, §6) ----------

    def _target_available(self) -> bool:
        """True once stage3 has unpacked — the target's ``/etc`` exists."""
        return os.path.isdir(rootpath.resolve(self._root, "/etc"))

    def _run_path(self) -> str:
        return os.path.join(self._run_dir, STATE_FILENAME)

    def _target_path(self) -> str:
        return paths.gest_state(STATE_FILENAME, self._root)

    def _state_path(self) -> str:
        """The active file for the current phase (recomputed each save/load)."""
        return self._target_path() if self._target_available() else self._run_path()

    def _load(self) -> None:
        """Union any on-disk marks into ``_done``. Never raises."""
        # Read both known files so a fresh store started after stage3 still finds
        # pre-stage3 marks; a missing/corrupt file loads as the empty set.
        paths_to_read = [self._run_path()]
        if self._target_available():
            paths_to_read.append(self._target_path())
        for path in paths_to_read:
            self._done |= self._read_file(path)

    def _save(self) -> None:
        path = self._state_path()
        if self._target_available():
            # Migration (§6): carry any pre-stage3 <run_dir> marks into the target
            # file so nothing already done is re-run. Idempotent — a plain union.
            self._done |= self._read_file(self._run_path())
        self._write_atomic(path, self._done)

    @staticmethod
    def _read_file(path: str) -> set[str]:
        """The completed keys stored at ``path`` (empty if missing/corrupt)."""
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            return {str(k) for k in data["done"]}
        except (OSError, ValueError, KeyError, TypeError):
            return set()

    @staticmethod
    def _write_atomic(path: str, done: set[str]) -> None:
        """Write ``{"done": [...]}`` atomically (temp file + ``os.replace``)."""
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        payload = json.dumps({"done": sorted(done)})
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".gest-state.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise


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
