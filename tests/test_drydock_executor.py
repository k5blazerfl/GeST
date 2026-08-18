"""CI-safe tests for the install-plan executor.

The orchestration is exercised with a fake runner (no host tools); the host
runner itself is validated on a machine, not in CI.
"""

from __future__ import annotations

import pytest

from gest.core.drydock import executor
from gest.core.drydock.executor import execute, host_run, render_write
from gest.core.drydock.interpreter import OP_COMMAND, OP_MANUAL, OP_WRITE, PlannedOp


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


# ---- OP_WRITE rendering (pure) -----------------------------------------
def _write(fmt, params, path="/x/out"):
    return PlannedOp(OP_WRITE, "w", detail={"path": path, "format": fmt, "params": params})


def test_render_write_file():
    path, content, mode = render_write(_write("file", {"content": "hello"}))
    assert (path, content, mode) == ("/x/out", "hello", "w")


def test_render_write_file_append_mode():
    _, _, mode = render_write(_write("file", {"content": "x", "mode": "append"}))
    assert mode == "a"


def test_render_write_config_ini():
    op = _write("config", {"section": "Net", "key": "port", "value": "3389"})
    _, content, mode = render_write(op)
    assert content == "[Net]\nport=3389\n" and mode == "w"


def test_render_write_json():
    _, content, _ = render_write(_write("json", {"data": {"a": 1}}))
    assert content == '{\n  "a": 1\n}'


# ---- host_run write ops (CI-safe: pure filesystem, no wine) -------------
def test_host_run_writes_file(tmp_path):
    target = tmp_path / "sub" / "conf.ini"
    op = _write("config", {"section": "S", "key": "k", "value": "v"}, str(target))
    assert host_run(op) == 0
    assert target.read_text() == "[S]\nk=v\n"  # parent dir created too


def test_host_run_chmodx(tmp_path):
    from gest.core.drydock.interpreter import OP_CHMODX
    f = tmp_path / "run.sh"
    f.write_text("#!/bin/sh\n")
    assert host_run(PlannedOp(OP_CHMODX, "x", detail={"path": str(f)})) == 0
    assert f.stat().st_mode & 0o111  # executable bits set


def test_host_run_unknown_op_fails():
    assert host_run(PlannedOp("bogus", "x")) == 1


# ---- CLI install (needs YAML to read the recipe file) ------------------
def test_cli_install_dry_run_and_real(tmp_path):
    pytest.importorskip("yaml")
    from gest.core.drydock import recipe_store
    from gest.core.drydock.recipe import Recipe, RecipeBarrel, RecipeStep
    from gest.tui.drydock.cli import CliIO, DrydockEnv, run_cli

    recipe = Recipe(app_name="Game", app_id="game",
                    barrel=RecipeBarrel(runner="wine", arch="win64"),
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
    from gest.core.drydock.recipe import Recipe, RecipeBarrel, RecipeStep
    from gest.tui.drydock.cli import CliIO, DrydockEnv, run_cli

    recipe = Recipe(app_name="Game", app_id="game",
                    barrel=RecipeBarrel(runner="wine", arch="win64"),
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
