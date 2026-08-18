"""CI-safe tests for the Lutris → helm.recipe importer.

The core :func:`convert` takes an already-parsed dict, so these run with no YAML
dependency. The YAML edges (:func:`load_script`/:func:`dump_recipe`) are covered
separately behind ``importorskip("yaml")``.
"""

from __future__ import annotations

import pytest

from gest.core.drydock import lutris_import, recipe
from gest.core.drydock.model import ARCH_WIN32, ARCH_WIN64, RUNNER_WINE


def _wine_script(**over) -> dict:
    base = {
        "name": "Some Game",
        "game_slug": "some-game",
        "runner": "wine",
        "wine": {"arch": "win32", "dxvk": True},
        "game": {"exe": "drive_c/game/game.exe", "args": "-windowed"},
        "files": [
            {"setup": "https://example.com/setup.exe"},
            {"patch": {"url": "https://example.com/p.zip", "filename": "patch.zip"}},
            {"disc": "N/A:Insert the original disc"},
        ],
        "installer": [
            {"task": {"name": "create_prefix", "arch": "win32"}},
            {"extract": {"file": "setup", "dst": "$GAMEDIR"}},
            {"task": {"name": "winetricks", "app": "dotnet48"}},
            {"execute": {"command": "patch.exe"}},
        ],
    }
    base.update(over)
    return base


def test_wine_script_converts_to_recipe():
    result = lutris_import.convert(_wine_script())
    assert result.ok and result.recipe is not None
    rec = result.recipe
    assert rec.app_name == "Some Game"
    assert rec.app_id == "some-game"
    assert rec.categories == ["Game"]
    assert rec.bottle.runner == RUNNER_WINE
    assert rec.bottle.arch == ARCH_WIN32
    assert rec.bottle.dxvk is True


def test_program_from_game_section():
    rec = lutris_import.convert(_wine_script()).recipe
    assert len(rec.programs) == 1
    prog = rec.programs[0]
    assert prog.exe == "drive_c/game/game.exe"
    assert prog.args == ["-windowed"]
    assert prog.category == "Game"


def test_files_map_url_dict_and_user_provided():
    rec = lutris_import.convert(_wine_script()).recipe
    by_id = {f.id: f for f in rec.files}
    assert by_id["setup"].url == "https://example.com/setup.exe"
    assert by_id["patch"].filename == "patch.zip"
    # "N/A:..." → a user-provided prompt, no URL.
    assert by_id["disc"].url == ""
    assert by_id["disc"].user_provided == "Insert the original disc"


def test_native_directives_and_tasks_become_steps():
    rec = lutris_import.convert(_wine_script()).recipe
    actions = [s.action for s in rec.steps]
    assert actions == [
        recipe.ACTION_CREATE_PREFIX,
        recipe.ACTION_EXTRACT,
        recipe.ACTION_WINETRICKS,
        recipe.ACTION_EXECUTE,
    ]
    # task 'name' is stripped from the emitted params.
    create = rec.steps[0]
    assert "name" not in create.params and create.params["arch"] == "win32"


def test_winetricks_verbs_collected_into_bottle():
    rec = lutris_import.convert(_wine_script()).recipe
    assert "dotnet48" in rec.bottle.verbs


def test_default_arch_is_win64():
    rec = lutris_import.convert(_wine_script(wine={})).recipe
    assert rec.bottle.arch == ARCH_WIN64


def test_non_wine_runner_is_rejected_whole():
    result = lutris_import.convert({"name": "DOS Game", "runner": "dosbox",
                                    "game": {"exe": "game.exe"}})
    assert not result.ok and result.recipe is None
    assert result.rejected and "dosbox" in result.rejected[0]


def test_reject_task_dropped_but_recipe_kept():
    result = lutris_import.convert(_wine_script(
        installer=[{"task": {"name": "dosexec", "executable": "x.exe"}}]))
    assert result.ok
    assert any("dosexec" in r for r in result.rejected)
    assert all(s.action != recipe.ACTION_MANUAL for s in result.recipe.steps)
    # a rejected task produces no step at all.
    assert result.recipe.steps == []


def test_flagged_directive_becomes_visible_manual_step():
    result = lutris_import.convert(_wine_script(
        installer=[{"input_menu": {"description": "pick one", "id": "choice"}}]))
    assert result.ok
    assert result.manual_steps == 1
    step = result.recipe.steps[0]
    assert step.action == recipe.ACTION_MANUAL
    assert step.params["original"] == "input_menu"
    assert any("input_menu" in w for w in result.warnings)


def test_unknown_task_flagged_as_manual():
    result = lutris_import.convert(_wine_script(
        installer=[{"task": {"name": "frobnicate", "x": 1}}]))
    assert result.manual_steps == 1
    assert result.recipe.steps[0].params["original"] == "task:frobnicate"


def test_system_env_mapped_other_system_flagged():
    result = lutris_import.convert(_wine_script(
        system={"env": {"DXVK_HUD": "fps"}, "disable_compositor": True}))
    assert result.recipe.bottle.env == {"DXVK_HUD": "fps"}
    assert any("disable_compositor" in w for w in result.warnings)


def test_missing_game_exe_warns_no_program():
    result = lutris_import.convert(_wine_script(game={}))
    assert result.recipe.programs == []
    assert any("no game.exe" in w for w in result.warnings)


def test_recipe_dict_round_trips():
    rec = lutris_import.convert(_wine_script()).recipe
    restored = recipe.Recipe.from_dict(rec.to_dict())
    assert restored.to_dict() == rec.to_dict()


def test_recipe_dict_shape_matches_adr_sketch():
    d = lutris_import.convert(_wine_script()).recipe.to_dict()
    assert d["recipe"] == recipe.RECIPE_VERSION
    assert set(d) == {"recipe", "app", "bottle", "files", "steps", "programs", "prereqs"}
    assert set(d["app"]) == {"name", "id", "categories"}


# --- YAML edges (only these need PyYAML) ------------------------------------

def test_load_script_flattens_website_export_wrapper():
    yaml = pytest.importorskip("yaml")
    text = yaml.safe_dump({
        "name": "Wrapped", "runner": "wine", "game_slug": "wrapped",
        "script": {"game": {"exe": "g.exe"}, "wine": {"arch": "win64"}},
    })
    flat = lutris_import.load_script(text)
    # metadata hoisted to the top level next to the inner script body.
    assert flat["runner"] == "wine"
    assert flat["name"] == "Wrapped"
    assert flat["game"]["exe"] == "g.exe"


def test_load_convert_dump_end_to_end():
    yaml = pytest.importorskip("yaml")
    text = yaml.safe_dump(_wine_script())
    result = lutris_import.convert(lutris_import.load_script(text))
    assert result.ok
    dumped = lutris_import.dump_recipe(result.recipe)
    reparsed = yaml.safe_load(dumped)
    assert reparsed["recipe"] == recipe.RECIPE_VERSION
    assert reparsed["app"]["name"] == "Some Game"


def test_load_script_rejects_non_mapping():
    pytest.importorskip("yaml")
    with pytest.raises(ValueError):
        lutris_import.load_script("- just\n- a\n- list\n")
