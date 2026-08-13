"""CI-safe tests for installer step 4d: the persistent ``StateStore`` (resume /
idempotency, design §6). Hermetic — every path is a ``tmp_path``; no test ever
touches a real ``/run`` or ``/etc``, and no disk/mount/network is involved.

What is pinned:

* ``StateStore()`` with no args stays a pure in-memory store (no file I/O), so the
  existing install-engine/registry/bootable tests are unchanged;
* a persistent store writes the two-phase location §6 prescribes — ``<run_dir>``
  before stage3, the target's ``/etc/portage/gest/`` once ``<root>/etc`` exists —
  and migrates the pre-stage3 marks across the boundary;
* a fresh persistent store on the same paths loads the marks, and ``run_install``
  therefore skips the already-completed (marker-gated) steps on a re-run;
* a missing or corrupt file loads as empty, never raising.
"""

import asyncio
import json
import os

from gest.core.exec.chroot import ChrootExecutor
from gest.core.exec.executor import FakeExecutor
from gest.core.exec.steps import Step
from gest.core.install.context import (
    STATE_FILENAME,
    InstallContext,
    StateStore,
)
from gest.core.install.engine import run_install
from gest.core.install.plan import Phase
from gest.core.install.step import ArgvStep
from gest.core.portage import paths

# ChrootExecutor guards its root under /mnt|/media|/run/media; the state store's
# persistence root (below) is an independent tmp_path, so the two never collide.
_ROOT = "/mnt/gentoo"


class _FakeStep:
    """Minimal stand-in for an ``InstallStep``: only ``key``/``label`` matter to
    ``StateStore.mark``."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.label = key


class _MarkerStep(ArgvStep):
    """A marker-gated chroot argv step, like ``SyncTree``/``EmergeWorld``: its
    ``is_satisfied`` reads only the state store, so a loaded mark short-circuits
    it (design §6)."""

    phase = Phase.BASE_SYSTEM
    chroot = True

    def __init__(self, label: str, key: str) -> None:
        self.label = label
        self.key = key

    def build(self, ctx):
        return [Step(self.label, ["run", self.key])]

    async def is_satisfied(self, ctx) -> bool:
        return ctx.state.done(self.key)


def _run_file(run_dir) -> str:
    return os.path.join(str(run_dir), STATE_FILENAME)


def _read_done(path: str) -> set[str]:
    with open(path, encoding="utf-8") as fh:
        return set(json.load(fh)["done"])


# --- 1. StateStore() with no args is in-memory only (unchanged) -------------

def test_no_arg_store_is_in_memory_and_writes_no_file(tmp_path, monkeypatch):
    # Run from an empty cwd and point the module's default run dir at a tmp dir:
    # if the no-arg store wrote anything, it would land in one of these.
    monkeypatch.chdir(tmp_path)
    store = StateStore()
    store.mark(_FakeStep("emerge_world"))
    assert store.done("emerge_world") is True
    assert store.done("sync_tree") is False
    # No persistence root ⇒ no file I/O of any kind.
    assert store._root is None
    assert list(tmp_path.iterdir()) == []


def test_default_context_state_is_in_memory():
    ctx = InstallContext(root=_ROOT, host=FakeExecutor(),
                         target=ChrootExecutor(FakeExecutor(), _ROOT))
    assert isinstance(ctx.state, StateStore)
    assert ctx.state._root is None


# --- 2. persist + reload before stage3 (target /etc absent → <run_dir>) ------

def test_persist_and_reload_before_stage3(tmp_path):
    target = str(tmp_path / "target")          # no <target>/etc yet
    run_dir = tmp_path / "run"

    store = StateStore(root=target, run_dir=str(run_dir))
    store.mark(_FakeStep("partition"))

    # Written under <run_dir>, not the (absent) target state dir.
    assert _read_done(_run_file(run_dir)) == {"partition"}
    assert not os.path.exists(paths.gest_state(STATE_FILENAME, target))

    # A fresh store on the same paths resumes the mark.
    reloaded = StateStore(root=target, run_dir=str(run_dir))
    assert reloaded.done("partition") is True


# --- 3. two-phase move: <run_dir> → target state dir, with migration ---------

def test_two_phase_move_migrates_run_marks_into_target(tmp_path):
    target = tmp_path / "target"
    run_dir = tmp_path / "run"

    store = StateStore(root=str(target), run_dir=str(run_dir))
    store.mark(_FakeStep("partition"))          # before stage3 → <run_dir>
    assert _read_done(_run_file(run_dir)) == {"partition"}

    # Stage3 lands: the target's /etc now exists → the location flips.
    os.makedirs(target / "etc")
    store.mark(_FakeStep("unpack_stage3"))

    target_file = paths.gest_state(STATE_FILENAME, str(target))
    assert os.path.exists(target_file)
    # The earlier /run mark was migrated in (union), so nothing already done reruns.
    assert _read_done(target_file) == {"partition", "unpack_stage3"}


# --- 4. resume skips completed marker-gated steps end-to-end ----------------

def _ctx(fx, state):
    return InstallContext(root=_ROOT, host=fx,
                          target=ChrootExecutor(fx, _ROOT), state=state)


def test_resume_skips_completed_steps_end_to_end(tmp_path):
    target = tmp_path / "target"
    run_dir = tmp_path / "run"
    os.makedirs(target / "etc")                 # durable (post-stage3) phase
    steps = [_MarkerStep("Sync the Portage tree", "sync_tree"),
             _MarkerStep("Emerge @world", "emerge_world")]

    # First run: nothing satisfied, both marker steps execute (and get persisted).
    fx1 = FakeExecutor()
    asyncio.run(run_install(_ctx(fx1, StateStore(root=str(target), run_dir=str(run_dir))),
                            steps))
    inner1 = [c[2:] for c in fx1.calls if c[:2] == ["chroot", _ROOT]]
    assert ["run", "sync_tree"] in inner1
    assert ["run", "emerge_world"] in inner1

    # Second run: a FRESH persistent store on the same paths loads the marks, so
    # is_satisfied short-circuits both steps — nothing runs.
    fx2 = FakeExecutor()
    asyncio.run(run_install(_ctx(fx2, StateStore(root=str(target), run_dir=str(run_dir))),
                            steps))
    assert fx2.calls == []


# --- 5. missing / corrupt file loads empty, never raising -------------------

def test_missing_file_loads_empty(tmp_path):
    store = StateStore(root=str(tmp_path / "target"), run_dir=str(tmp_path / "run"))
    assert store.done("anything") is False


def test_corrupt_file_loads_empty_and_can_be_overwritten(tmp_path):
    run_dir = tmp_path / "run"
    os.makedirs(run_dir)
    (run_dir / STATE_FILENAME).write_text("}{ not json", encoding="utf-8")
    target = str(tmp_path / "target")

    store = StateStore(root=target, run_dir=str(run_dir))     # must not raise
    assert store.done("partition") is False

    # A later mark writes a clean file over the garbage.
    store.mark(_FakeStep("partition"))
    assert _read_done(_run_file(run_dir)) == {"partition"}
