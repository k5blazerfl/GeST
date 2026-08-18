"""Execute a compiled install plan (:mod:`.interpreter`).

The **sequencing** is pure and CI-testable: iterate the ops, honour dry-run, halt
on a manual step or a failure, and collect a per-op report. The **work** itself
(spawning wine, unpacking archives, moving files) is delegated to an injected
``runner`` callable — its default, :func:`host_run`, is host-only and validated
on a real machine, not in CI (like live launch).

Roadmap phase 6 — the piece that turns a plan into an installed bottle.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

from gest.core.drydock import interpreter as I
from gest.core.drydock.interpreter import PlannedOp

STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_MANUAL = "manual"  # a step a human must complete — execution halts here
STATUS_PLANNED = "planned"  # dry run: would run, not executed
STATUS_SKIPPED = "skipped"  # not reached (a prior step halted the run)

# A runner performs one op and returns an exit code (0 == success).
Runner = Callable[[PlannedOp], int]


@dataclass(slots=True)
class StepOutcome:
    op: PlannedOp
    status: str
    code: int = 0


@dataclass(slots=True)
class ExecReport:
    outcomes: list[StepOutcome] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when nothing failed and nothing was left unreached — a manual
        halt or a failure both make the run incomplete."""
        return not any(o.status in (STATUS_FAILED, STATUS_SKIPPED) for o in self.outcomes)

    def count(self, status: str) -> int:
        return sum(1 for o in self.outcomes if o.status == status)


def execute(plan: list[PlannedOp], runner: Runner, *, dry_run: bool = False,
            stop_on_manual: bool = True) -> ExecReport:
    """Run ``plan`` through ``runner`` in order. A manual step halts the run
    (unless ``stop_on_manual`` is False); a failed op halts it; every op after a
    halt is recorded as ``skipped``. In ``dry_run`` the runner is never called."""
    report = ExecReport()
    halted = False
    for op in plan:
        if halted:
            report.outcomes.append(StepOutcome(op, STATUS_SKIPPED))
            continue
        if op.kind == I.OP_MANUAL:
            report.outcomes.append(StepOutcome(op, STATUS_MANUAL))
            if stop_on_manual and not dry_run:
                halted = True
            continue
        if dry_run:
            report.outcomes.append(StepOutcome(op, STATUS_PLANNED))
            continue
        code = runner(op)
        status = STATUS_OK if code == 0 else STATUS_FAILED
        report.outcomes.append(StepOutcome(op, status, code))
        if code != 0:
            halted = True
    return report


def render_write(op: PlannedOp) -> tuple[str, str, str]:
    """Render an ``OP_WRITE`` into ``(path, content, mode)`` — **pure**, so the
    content is unit-testable; the host runner just opens the path and writes.

    ``write_json`` → pretty JSON of ``data``; ``write_config`` → an INI stanza
    (``[section]`` + ``key=value``); ``write_file`` → raw ``content`` (``mode``
    is ``"a"`` when the step asked to append, else ``"w"``)."""
    path = op.detail["path"]
    fmt = op.detail.get("format", "file")
    params = op.detail.get("params", {})
    if fmt == "json":
        return path, json.dumps(params.get("data", {}), indent=2), "w"
    if fmt == "config":
        section, key = params.get("section", ""), params.get("key", "")
        body = (f"[{section}]\n" if section else "") + f"{key}={params.get('value', '')}\n"
        return path, body, "w"
    mode = "a" if str(params.get("mode", "")).lower() == "append" else "w"
    return path, str(params.get("content", "")), mode


def host_run(op: PlannedOp) -> int:
    """Default runner — performs an op for real. Command ops spawn processes
    (**host-only**, not exercised in CI); the filesystem ops touch disk. Returns
    an exit code."""
    try:
        if op.kind == I.OP_COMMAND:
            return subprocess.run(op.argv, env={**os.environ, **op.env}).returncode
        if op.kind == I.OP_CHMODX:
            path = op.detail["path"]
            os.chmod(path, os.stat(path).st_mode | 0o111)
            return 0
        if op.kind in (I.OP_MOVE, I.OP_COPY):
            src, dst = op.detail["src"], op.detail["dst"]
            if op.kind == I.OP_MOVE:
                shutil.move(src, dst)
            elif os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            return 0
        if op.kind == I.OP_EXTRACT:
            os.makedirs(op.detail["dst"], exist_ok=True)
            shutil.unpack_archive(op.detail["src"], op.detail["dst"])
            return 0
        if op.kind == I.OP_WRITE:
            path, content, mode = render_write(op)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, mode, encoding="utf-8") as handle:
                handle.write(content)
            return 0
    except (OSError, shutil.Error, ValueError):
        return 1
    # An unrecognised op kind — surface rather than silently succeed.
    return 1
