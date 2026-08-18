"""CI-safe tests for the recipe interpreter (recipe → install plan).

The planner is pure (no YAML, no host tools); the CLI `plan` path reads a
helm.recipe file, so that one test ``importorskip("yaml")``.
"""

from __future__ import annotations

import pytest

from gest.core.drydock import interpreter
from gest.core.drydock.interpreter import PlanContext, plan
from gest.core.drydock.recipe import Recipe, RecipeBarrel, RecipeFile, RecipeStep


def _ctx(**over) -> PlanContext:
    base = dict(prefix="/pfx", gamedir="/pfx/drive_c/game", cache="/cache", arch="win64")
    base.update(over)
    return PlanContext(**base)


def _recipe(steps, files=None) -> Recipe:
    return Recipe(app_name="Game", app_id="game",
                  barrel=RecipeBarrel(runner="wine", arch="win64"),
                  files=files or [], steps=steps)


def test_create_prefix_plans_wineboot():
    ops = plan(_recipe([RecipeStep("create_prefix", {"arch": "win64"})]), _ctx())
    assert ops[0].kind == interpreter.OP_COMMAND
    assert ops[0].argv == ["wineboot", "-i"]
    assert ops[0].env == {"WINEPREFIX": "/pfx", "WINEARCH": "win64"}


def test_winetricks_plans_verbs():
    ops = plan(_recipe([RecipeStep("winetricks", {"app": "dotnet48"})]), _ctx())
    assert ops[0].argv == ["winetricks", "-q", "dotnet48"]


def test_winetricks_list_of_verbs():
    ops = plan(_recipe([RecipeStep("winetricks", {"app": ["vcrun2019", "dotnet48"]})]), _ctx())
    assert ops[0].argv == ["winetricks", "-q", "vcrun2019", "dotnet48"]


def test_wineexec_substitutes_variables():
    step = RecipeStep("wineexec", {"executable": "$GAMEDIR/setup.exe", "args": "/silent"})
    ops = plan(_recipe([step]), _ctx())
    assert ops[0].argv == ["wine", "/pfx/drive_c/game/setup.exe", "/silent"]


def test_extract_resolves_file_id_to_cache_path():
    recipe = _recipe(
        steps=[RecipeStep("extract", {"file": "setup", "dst": "$GAMEDIR"})],
        files=[RecipeFile(id="setup", url="https://x/setup.exe")])
    ops = plan(recipe, _ctx())
    assert ops[0].kind == interpreter.OP_EXTRACT
    assert ops[0].detail["src"] == "/cache/setup.exe"  # id → cached filename
    assert ops[0].detail["dst"] == "/pfx/drive_c/game"  # $GAMEDIR resolved


def test_extract_default_dst_is_gamedir():
    ops = plan(_recipe([RecipeStep("extract", {"file": "/abs/a.zip"})]), _ctx())
    assert ops[0].detail["dst"] == "/pfx/drive_c/game"


def test_write_ops_carry_format():
    ops = plan(_recipe([
        RecipeStep("write_file", {"file": "$GAMEDIR/x.ini"}),
        RecipeStep("write_json", {"path": "$GAMEDIR/y.json"}),
    ]), _ctx())
    assert ops[0].kind == interpreter.OP_WRITE and ops[0].detail["format"] == "file"
    assert ops[0].detail["path"] == "/pfx/drive_c/game/x.ini"
    assert ops[1].detail["format"] == "json"


def test_chmodx_and_move():
    ops = plan(_recipe([
        RecipeStep("chmodx", {"file": "$GAMEDIR/run.sh"}),
        RecipeStep("move", {"src": "$CACHE/a", "dst": "$GAMEDIR/a"}),
    ]), _ctx())
    assert ops[0].kind == interpreter.OP_CHMODX and ops[0].detail["path"].endswith("/run.sh")
    assert ops[1].kind == interpreter.OP_MOVE
    assert ops[1].detail == {"src": "/cache/a", "dst": "/pfx/drive_c/game/a"}


def test_manual_step_passes_through():
    ops = plan(_recipe([RecipeStep("manual", {"original": "input_menu"})]), _ctx())
    assert ops[0].kind == interpreter.OP_MANUAL
    assert ops[0].detail["original"] == "input_menu"


def test_regedit_file_and_winekill():
    ops = plan(_recipe([
        RecipeStep("regedit_file", {"file": "$GAMEDIR/tweak.reg"}),
        RecipeStep("winekill", {}),
    ]), _ctx())
    assert ops[0].argv == ["wine", "regedit", "/pfx/drive_c/game/tweak.reg"]
    assert ops[1].argv == ["wineserver", "-k"]


def test_proton_command_steps_become_manual():
    recipe = Recipe(app_name="G", app_id="g",
                    barrel=RecipeBarrel(runner="proton", arch="win64"),
                    steps=[RecipeStep("winetricks", {"app": "dxvk"}),
                           RecipeStep("extract", {"file": "/a.zip", "dst": "$GAMEDIR"})])
    ops = plan(recipe, _ctx(runner="proton"))
    # command step → manual note; filesystem step still plans.
    assert ops[0].kind == interpreter.OP_MANUAL and "Proton" in ops[0].summary
    assert ops[1].kind == interpreter.OP_EXTRACT


def test_planned_op_to_dict():
    op = plan(_recipe([RecipeStep("create_prefix", {})]), _ctx())[0]
    d = op.to_dict()
    assert set(d) == {"kind", "summary", "argv", "env", "detail"}


# ---- CLI (needs YAML to read the recipe file) --------------------------
def test_cli_plan_prints_ops(tmp_path):
    pytest.importorskip("yaml")
    from gest.core.drydock import recipe_store
    from gest.tui.drydock.cli import CliIO, DrydockEnv, run_cli
    recipe = _recipe([RecipeStep("create_prefix", {"arch": "win64"}),
                      RecipeStep("winetricks", {"app": "dotnet48"})])
    path = tmp_path / "game.recipe"
    path.write_text(recipe_store.dumps(recipe), encoding="utf-8")
    out: list[str] = []
    env = DrydockEnv(io=CliIO(out=out.append, err=out.append))
    assert run_cli(["plan", str(path)], env=env) == 0
    joined = "\n".join(out)
    assert "wineboot" in joined and "winetricks" in joined
    assert "2 op(s): 2 command(s)" in joined
