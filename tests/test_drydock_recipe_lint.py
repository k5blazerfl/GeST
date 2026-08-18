"""CI-safe tests for the helm.recipe linter."""

from __future__ import annotations

import pytest

from gest.core.drydock import recipe_lint
from gest.core.drydock.recipe import (
    Recipe,
    RecipeBottle,
    RecipeFile,
    RecipeProgram,
    RecipeStep,
)


def _ok_recipe(**over) -> Recipe:
    base = dict(
        app_name="Game", app_id="game",
        bottle=RecipeBottle(runner="wine", arch="win64"),
        files=[RecipeFile(id="setup", url="https://x/setup.exe")],
        programs=[RecipeProgram(name="Game", exe="drive_c/game.exe")],
        steps=[RecipeStep("extract", {"file": "setup", "dst": "$GAMEDIR"})],
    )
    base.update(over)
    return Recipe(**base)


def _levels(issues):
    return {i.level for i in issues}


def test_clean_recipe_has_no_issues():
    assert recipe_lint.lint(_ok_recipe()) == []
    assert not recipe_lint.has_errors([])


def test_bad_runner_and_arch_are_errors():
    issues = recipe_lint.lint(_ok_recipe(bottle=RecipeBottle(runner="dosbox", arch="win128")))
    assert recipe_lint.has_errors(issues)
    text = " ".join(i.message for i in issues)
    assert "runner" in text and "arch" in text


def test_program_without_exe_is_error():
    issues = recipe_lint.lint(_ok_recipe(programs=[RecipeProgram(name="X", exe="")]))
    assert recipe_lint.has_errors(issues)


def test_no_programs_is_warning_not_error():
    issues = recipe_lint.lint(_ok_recipe(programs=[]))
    assert not recipe_lint.has_errors(issues)
    assert recipe_lint.WARNING in _levels(issues)


def test_unknown_action_is_error():
    issues = recipe_lint.lint(_ok_recipe(steps=[RecipeStep("frobnicate", {})]))
    assert recipe_lint.has_errors(issues)
    assert any("unknown action" in i.message for i in issues)


def test_manual_step_is_warning():
    issues = recipe_lint.lint(_ok_recipe(
        steps=[RecipeStep("manual", {"original": "input_menu"})]))
    assert not recipe_lint.has_errors(issues)
    assert any("manual step" in i.message and "input_menu" in i.message for i in issues)


def test_extract_unresolved_file_id_is_warning():
    issues = recipe_lint.lint(_ok_recipe(
        files=[],  # 'setup' no longer declared
        steps=[RecipeStep("extract", {"file": "setup", "dst": "$GAMEDIR"})]))
    assert not recipe_lint.has_errors(issues)
    assert any("no files entry provides" in i.message for i in issues)


def test_extract_path_or_variable_not_flagged():
    # a path or a $VAR is not a file id — should not warn.
    issues = recipe_lint.lint(_ok_recipe(
        files=[], steps=[RecipeStep("extract", {"file": "/abs/a.zip"}),
                         RecipeStep("extract", {"file": "$CACHE/b.zip"})]))
    assert not any("no files entry provides" in i.message for i in issues)


def test_file_without_source_is_warning():
    issues = recipe_lint.lint(_ok_recipe(files=[RecipeFile(id="setup")]))
    assert any("neither a url" in i.message for i in issues)


def test_empty_app_name_is_error():
    assert recipe_lint.has_errors(recipe_lint.lint(_ok_recipe(app_name="")))


# ---- CLI (needs YAML to read the recipe file) --------------------------
def test_cli_lint_clean_and_broken(tmp_path):
    pytest.importorskip("yaml")
    from gest.core.drydock import recipe_store
    from gest.tui.drydock.cli import CliIO, DrydockEnv, run_cli

    good = tmp_path / "good.recipe"
    good.write_text(recipe_store.dumps(_ok_recipe()), encoding="utf-8")
    out: list[str] = []
    env = DrydockEnv(io=CliIO(out=out.append, err=out.append))
    assert run_cli(["lint", str(good)], env=env) == 0
    assert any("no issues" in line for line in out)

    bad = tmp_path / "bad.recipe"
    bad.write_text(recipe_store.dumps(_ok_recipe(steps=[RecipeStep("frobnicate", {})])),
                   encoding="utf-8")
    out.clear()
    assert run_cli(["lint", str(bad)], env=env) == 1  # errors → nonzero exit
    assert any("error:" in line for line in out)
