"""CI-safe tests for the install-plan executor.

The orchestration is exercised with a fake runner (no host tools); the host
runner itself is validated on a machine, not in CI.
"""

from __future__ import annotations

import pytest

from gest.core.drydock import executor
from gest.core.drydock.executor import execute
from gest.core.drydock.interpreter import OP_COMMAND, OP_MANUAL, PlannedOp


def _cmd(summary="cmd"):
    return PlannedOp(OP_COMMAND, summary, argv=["true"])


def _fake_runner(fail_on=()):
    calls: list = []

    def run(op):
        calls.append(op)
        return 1 if op.summary in fail_on else 0

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_all_ok():
    runner = _fake_runner()
    report = execute([_cmd("a"), _cmd("b")], runner)
    assert report.ok
    assert [o.status for o in report.outcomes] == [executor.STATUS_OK, executor.STATUS_OK]
    assert len(runner.calls) == 2


def test_dry_run_never_calls_runner():
    runner = _fake_runner()
    report = execute([_cmd("a"), _cmd("b")], runner, dry_run=True)
    assert report.ok
    assert all(o.status == executor.STATUS_PLANNED for o in report.outcomes)
    assert runner.calls == []


def test_failure_halts_and_skips_rest():
    runner = _fake_runner(fail_on={"b"})
    report = execute([_cmd("a"), _cmd("b"), _cmd("c")], runner)
    assert not report.ok
    assert [o.status for o in report.outcomes] == [
        executor.STATUS_OK, executor.STATUS_FAILED, executor.STATUS_SKIPPED]
    assert len(runner.calls) == 2  # c never attempted


def test_manual_halts_by_default():
    runner = _fake_runner()
    plan = [_cmd("a"), PlannedOp(OP_MANUAL, "do it by hand"), _cmd("c")]
    report = execute(plan, runner)
    assert not report.ok
    assert [o.status for o in report.outcomes] == [
        executor.STATUS_OK, executor.STATUS_MANUAL, executor.STATUS_SKIPPED]
    assert len(runner.calls) == 1


def test_manual_can_continue_when_not_stopping():
    runner = _fake_runner()
    plan = [_cmd("a"), PlannedOp(OP_MANUAL, "note"), _cmd("c")]
    report = execute(plan, runner, stop_on_manual=False)
    assert [o.status for o in report.outcomes] == [
        executor.STATUS_OK, executor.STATUS_MANUAL, executor.STATUS_OK]
    assert len(runner.calls) == 2


def test_dry_run_does_not_halt_on_manual():
    runner = _fake_runner()
    plan = [PlannedOp(OP_MANUAL, "note"), _cmd("b")]
    report = execute(plan, runner, dry_run=True)
    assert [o.status for o in report.outcomes] == [
        executor.STATUS_MANUAL, executor.STATUS_PLANNED]


def test_count_helper():
    report = execute([_cmd("a"), _cmd("b")], _fake_runner(), dry_run=True)
    assert report.count(executor.STATUS_PLANNED) == 2
    assert report.count(executor.STATUS_OK) == 0


# ---- CLI install (needs YAML to read the recipe file) ------------------
def test_cli_install_dry_run_and_real(tmp_path):
    pytest.importorskip("yaml")
    from gest.core.drydock import recipe_store
    from gest.core.drydock.recipe import Recipe, RecipeBottle, RecipeStep
    from gest.tui.drydock.cli import CliIO, DrydockEnv, run_cli

    recipe = Recipe(app_name="Game", app_id="game",
                    bottle=RecipeBottle(runner="wine", arch="win64"),
                    steps=[RecipeStep("create_prefix", {"arch": "win64"}),
                           RecipeStep("winetricks", {"app": "dotnet48"})])
    path = tmp_path / "game.recipe"
    path.write_text(recipe_store.dumps(recipe), encoding="utf-8")

    calls: list = []
    env = DrydockEnv(io=CliIO(out=(out := []).append, err=out.append),
                     step_runner=lambda op: calls.append(op) or 0)

    # dry run (default): plan shown, runner never called.
    assert run_cli(["install", str(path)], env=env) == 0
    assert calls == []
    assert any("planned" in line for line in out)

    # real run: the injected runner executes both command ops.
    out.clear()
    assert run_cli(["install", str(path), "--run"], env=env) == 0
    assert len(calls) == 2
    assert "2 ok" in "\n".join(out)


def test_cli_install_refuses_recipe_with_lint_errors(tmp_path):
    pytest.importorskip("yaml")
    from gest.core.drydock import recipe_store
    from gest.core.drydock.recipe import Recipe, RecipeBottle, RecipeStep
    from gest.tui.drydock.cli import CliIO, DrydockEnv, run_cli

    recipe = Recipe(app_name="Game", app_id="game",
                    bottle=RecipeBottle(runner="wine", arch="win64"),
                    steps=[RecipeStep("frobnicate", {})])  # unknown action → lint error
    path = tmp_path / "bad.recipe"
    path.write_text(recipe_store.dumps(recipe), encoding="utf-8")
    calls: list = []
    env = DrydockEnv(io=CliIO(out=(out := []).append, err=out.append),
                     step_runner=lambda op: calls.append(op) or 0)
    # refuses, runs nothing…
    assert run_cli(["install", str(path), "--run"], env=env) == 1
    assert calls == []
    # …unless overridden.
    assert run_cli(["install", str(path), "--run", "--no-lint"], env=env) == 0
