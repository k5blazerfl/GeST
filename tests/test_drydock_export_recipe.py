"""CI-safe tests for exporting a bottle back to a helm.recipe."""

from __future__ import annotations

import pytest

from gest.core.drydock import bottles, materialize
from gest.core.drydock.model import Bottle, Program
from gest.tui.drydock.cli import CliIO, DrydockEnv, run_cli


def _bottle(**over) -> Bottle:
    base = dict(id="office", name="Office", runner="wine", arch="win32",
                verbs=["dotnet48"], dxvk=True, env={"WINEDEBUG": "-all"})
    base.update(over)
    b = Bottle(**base)
    b.programs.append(Program(id="excel", name="Excel", exe="C:/office/excel.exe",
                              args=["/x"], category="Application"))
    return b


# ---- pure inverse bridge ----------------------------------------------
def test_recipe_from_bottle_maps_config():
    recipe = materialize.recipe_from_bottle(_bottle())
    assert recipe.app_name == "Office" and recipe.app_id == "office"
    assert recipe.bottle.runner == "wine" and recipe.bottle.arch == "win32"
    assert recipe.bottle.verbs == ["dotnet48"] and recipe.bottle.dxvk is True
    assert recipe.bottle.env == {"WINEDEBUG": "-all"}
    assert recipe.steps == [] and recipe.files == []  # a bottle keeps no install steps
    assert len(recipe.programs) == 1
    assert recipe.programs[0].exe == "C:/office/excel.exe"


def test_category_game_when_any_program_is_game():
    b = _bottle()
    b.programs.append(Program(id="doom", name="Doom", exe="d.exe", category="Game"))
    assert materialize.recipe_from_bottle(b).categories == ["Game"]


def test_materialize_export_round_trips_config():
    original = _bottle()
    recipe = materialize.recipe_from_bottle(original)
    rebuilt = materialize.bottle_from_recipe(recipe)
    assert (rebuilt.runner, rebuilt.arch, rebuilt.verbs, rebuilt.dxvk, rebuilt.env) == \
           (original.runner, original.arch, original.verbs, original.dxvk, original.env)
    assert [p.exe for p in rebuilt.programs] == [p.exe for p in original.programs]


# ---- CLI (needs YAML to render) ---------------------------------------
def test_cli_export_recipe_to_file(tmp_path):
    pytest.importorskip("yaml")
    store = str(tmp_path / "bottles")
    bottles.save_bottle(_bottle(), store)
    out: list[str] = []
    env = DrydockEnv(io=CliIO(out=out.append, err=out.append), store_base=store)
    dest = tmp_path / "office.recipe"
    assert run_cli(["export-recipe", "office", "-o", str(dest)], env=env) == 0
    text = dest.read_text()
    assert "recipe:" in text and "office" in text and "dotnet48" in text


def test_cli_export_recipe_stdout(tmp_path):
    pytest.importorskip("yaml")
    store = str(tmp_path / "bottles")
    bottles.save_bottle(_bottle(), store)
    out: list[str] = []
    env = DrydockEnv(io=CliIO(out=out.append, err=out.append), store_base=store)
    assert run_cli(["export-recipe", "office"], env=env) == 0
    assert any("app:" in line for line in out)


def test_cli_export_recipe_unknown_bottle(tmp_path):
    err: list[str] = []
    env = DrydockEnv(io=CliIO(out=err.append, err=err.append),
                     store_base=str(tmp_path / "bottles"))
    assert run_cli(["export-recipe", "nope"], env=env) == 1
