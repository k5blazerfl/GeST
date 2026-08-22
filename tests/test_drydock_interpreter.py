"""CI-safe tests for the recipe interpreter (recipe → install plan).

The planner is pure (no YAML, no host tools); the CLI `plan` path reads a
helm.recipe file, so that one test ``importorskip("yaml")``.
"""

from __future__ import annotations

import pytest

from gest.core.drydock import interpreter, lutris_import
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


def test_execute_regedit_regdelete_eject_are_wired_not_manual():
    # these were once recognised-but-unwired (`manual` TODOs); they now plan to
    # real commands. Only a genuine `manual` action stays manual.
    for action in ("execute", "regedit", "regdelete", "eject_disc"):
        ops = plan(_recipe([RecipeStep(action, {"command": "x.exe", "key": "K",
                                                "path": "P", "value": "v"})]), _ctx())
        assert ops[0].kind == interpreter.OP_COMMAND, action
    manual = plan(_recipe([RecipeStep("manual", {"original": "input_menu"})]), _ctx())
    assert manual[0].kind == interpreter.OP_MANUAL


def test_regedit_file_and_winekill():
    ops = plan(_recipe([
        RecipeStep("regedit_file", {"file": "$GAMEDIR/tweak.reg"}),
        RecipeStep("winekill", {}),
    ]), _ctx())
    assert ops[0].argv == ["wine", "regedit", "/pfx/drive_c/game/tweak.reg"]
    assert ops[1].argv == ["wineserver", "-k"]


def _proton_recipe(steps) -> Recipe:
    return Recipe(app_name="G", app_id="g",
                  barrel=RecipeBarrel(runner="proton", arch="win64"), steps=steps)


def test_proton_command_steps_route_through_umu():
    recipe = _proton_recipe([RecipeStep("winetricks", {"app": "vcrun2019"}),
                             RecipeStep("extract", {"file": "/a.zip", "dst": "$GAMEDIR"})])
    ops = plan(recipe, _ctx(runner="proton"))
    # command step → a real umu-run command (no longer a manual stub)…
    assert ops[0].kind == interpreter.OP_COMMAND
    assert ops[0].argv == ["umu-run", "winetricks", "-q", "vcrun2019"]
    # …and the filesystem step still plans runner-agnostically.
    assert ops[1].kind == interpreter.OP_EXTRACT


def test_proton_create_prefix_uses_umu_createprefix():
    ops = plan(_proton_recipe([RecipeStep("create_prefix", {})]), _ctx(runner="proton"))
    assert ops[0].kind == interpreter.OP_COMMAND
    assert ops[0].argv == ["umu-run", "createprefix"]


def test_proton_wineexec_and_regedit_and_winekill():
    ops = plan(_proton_recipe([
        RecipeStep("wineexec", {"exe": "$CACHE/setup.exe", "args": ["/S"]}),
        RecipeStep("regedit_file", {"file": "$GAMEDIR/tweak.reg"}),
        RecipeStep("winekill", {}),
    ]), _ctx(runner="proton"))
    assert ops[0].argv == ["umu-run", "/cache/setup.exe", "/S"]
    assert ops[1].argv == ["umu-run", "regedit", "/pfx/drive_c/game/tweak.reg"]
    assert ops[2].argv == ["umu-run", "wineserver", "-k"]


def test_proton_env_has_umu_essentials_and_protonpath():
    ops = plan(_proton_recipe([RecipeStep("wineexec", {"exe": "x.exe"})]),
               _ctx(runner="proton", runner_version="GE-Proton9-20"))
    env = ops[0].env
    assert env["WINEPREFIX"] == "/pfx"
    assert env["GAMEID"] == "umu-0" and env["STORE"] == "none"
    assert env["PROTONPATH"] == "GE-Proton9-20"  # the barrel's pinned Proton


def test_proton_env_omits_protonpath_when_unpinned():
    # a recipe-only plan has no Proton pin → umu falls back to its default build.
    ops = plan(_proton_recipe([RecipeStep("wineexec", {"exe": "x.exe"})]), _ctx(runner="proton"))
    assert "PROTONPATH" not in ops[0].env


# ---- regedit / regdelete (were manual until wired) ---------------------
def test_regedit_sets_a_value_via_reg_add():
    ops = plan(_recipe([RecipeStep("regedit", {
        "path": r"HKEY_CURRENT_USER\Software\Game", "key": "Lang",
        "value": "en", "type": "REG_SZ"})]), _ctx())
    assert ops[0].kind == interpreter.OP_COMMAND
    assert ops[0].argv == ["wine", "reg", "add", r"HKEY_CURRENT_USER\Software\Game",
                           "/v", "Lang", "/t", "REG_SZ", "/d", "en", "/f"]


def test_regedit_default_value_and_default_type():
    ops = plan(_recipe([RecipeStep("regedit",
                                   {"path": r"HKCU\Software\G", "value": "1"})]), _ctx())
    # no value name → /ve (the key's default value); no type → REG_SZ.
    assert ops[0].argv == ["wine", "reg", "add", r"HKCU\Software\G",
                           "/ve", "/t", "REG_SZ", "/d", "1", "/f"]


def test_regdelete_removes_a_key():
    ops = plan(_recipe([RecipeStep("regdelete", {"key": r"HKCU\Software\Game"})]), _ctx())
    assert ops[0].argv == ["wine", "reg", "delete", r"HKCU\Software\Game", "/f"]


def test_regedit_and_regdelete_route_through_umu_on_proton():
    ops = plan(_proton_recipe([
        RecipeStep("regedit", {"path": r"HKCU\S\G", "key": "V", "value": "x"}),
        RecipeStep("regdelete", {"key": r"HKCU\S\G"}),
    ]), _ctx(runner="proton"))
    assert ops[0].argv[:3] == ["umu-run", "reg", "add"]
    assert ops[1].argv == ["umu-run", "reg", "delete", r"HKCU\S\G", "/f"]
    assert ops[0].env["GAMEID"] == "umu-0"  # umu env, not wine env


# ---- execute (Windows exe → runner; native → direct) -------------------
def test_execute_windows_exe_runs_through_wine():
    ops = plan(_recipe([RecipeStep("execute", {"command": "patch.exe", "args": ["/S"]})]), _ctx())
    assert ops[0].argv == ["wine", "patch.exe", "/S"]
    assert ops[0].env["WINEPREFIX"] == "/pfx"


def test_execute_windows_exe_runs_through_umu_on_proton():
    ops = plan(_proton_recipe([RecipeStep("execute", {"exe": "setup.exe"})]),
               _ctx(runner="proton"))
    assert ops[0].argv == ["umu-run", "setup.exe"]


def test_execute_native_command_runs_directly():
    ops = plan(_recipe([RecipeStep("execute", {"command": "unzip", "args": ["a.zip"]})]), _ctx())
    # not a .exe → a native host command, no wine wrapper, no wine env.
    assert ops[0].argv == ["unzip", "a.zip"]
    assert ops[0].env == {} and ops[0].detail.get("native") is True


def test_execute_file_id_resolves_to_cached_path():
    recipe = _recipe([RecipeStep("execute", {"file": "inst"})],
                     files=[RecipeFile(id="inst", url="https://x/inst.exe")])
    ops = plan(recipe, _ctx())
    assert ops[0].argv == ["wine", "/cache/inst.exe"]


# ---- importer → interpreter loop closed (no plan-time manual regressions) --
def test_lutris_registry_and_execute_tasks_plan_end_to_end():
    # a Lutris script whose tasks the importer maps natively must now plan to real
    # commands — this was the gap: importer emitted them, interpreter dropped them.
    script = {
        "runner": "wine", "name": "G", "game_slug": "g",
        "installer": [
            {"task": {"name": "set_regedit", "path": r"HKCU\Software\G",
                      "key": "Lang", "value": "en"}},
            {"task": {"name": "delete_registry_key", "key": r"HKCU\Software\G\Tmp"}},
            {"task": {"name": "eject_disc"}},
            {"execute": {"command": "post.exe"}},
        ],
    }
    result = lutris_import.convert(script)
    assert result.manual_steps == 0  # importer mapped them natively
    ops = plan(result.recipe, _ctx())
    kinds = {op.kind for op in ops}
    assert kinds == {interpreter.OP_COMMAND}  # …and none fall back to manual at plan time
    assert ops[0].argv[:3] == ["wine", "reg", "add"]
    assert ops[1].argv[:3] == ["wine", "reg", "delete"]
    assert ops[2].argv == ["eject"]
    assert ops[3].argv == ["wine", "post.exe"]


# ---- eject_disc (runner-agnostic) --------------------------------------
def test_eject_disc_plans_eject():
    ops = plan(_recipe([RecipeStep("eject_disc", {})]), _ctx())
    assert ops[0].kind == interpreter.OP_COMMAND and ops[0].argv == ["eject"]
    # runner-agnostic — same on Proton, no umu wrapper.
    proton = plan(_proton_recipe([RecipeStep("eject_disc", {})]), _ctx(runner="proton"))
    assert proton[0].argv == ["eject"]


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
