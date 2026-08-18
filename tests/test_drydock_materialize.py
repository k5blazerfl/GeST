"""CI-safe tests for recipe → bottle materialization and the `materialize` CLI.

The pure ``bottle_from_recipe`` bridge needs no YAML; the file-based CLI path
reads a helm.recipe, so those tests ``importorskip("yaml")``.
"""

from __future__ import annotations

import pytest

from gest.core.customs import identity_store
from gest.core.drydock import bottles, materialize, recipe_store
from gest.core.drydock.recipe import Recipe, RecipeBottle, RecipeProgram
from gest.tui.drydock.cli import CliIO, DrydockEnv, run_cli


def _recipe(**over) -> Recipe:
    base = dict(
        app_name="Some Game", app_id="some-game", categories=["Game"],
        bottle=RecipeBottle(runner="wine", arch="win32", verbs=["dotnet48"], dxvk=True),
        programs=[RecipeProgram(name="Some Game", exe="drive_c/game/game.exe",
                                args=["-w"], category="Game")],
    )
    base.update(over)
    return Recipe(**base)


# ---- pure bridge -------------------------------------------------------
def test_bottle_from_recipe_maps_fields():
    bottle = materialize.bottle_from_recipe(_recipe())
    assert bottle.id == "some-game"
    assert bottle.name == "Some Game"
    assert bottle.runner == "wine" and bottle.arch == "win32"
    assert bottle.verbs == ["dotnet48"] and bottle.dxvk is True
    assert len(bottle.programs) == 1
    prog = bottle.programs[0]
    assert prog.exe == "drive_c/game/game.exe" and prog.args == ["-w"]
    assert prog.category == "Game"


def test_bottle_id_override():
    bottle = materialize.bottle_from_recipe(_recipe(), bottle_id="My Bottle")
    assert bottle.id == "my-bottle"


def test_program_ids_deduped():
    rec = _recipe(programs=[
        RecipeProgram(name="Editor", exe="a.exe"),
        RecipeProgram(name="Editor", exe="b.exe"),  # same name → same base id
    ])
    bottle = materialize.bottle_from_recipe(rec)
    ids = [p.id for p in bottle.programs]
    assert ids == ["editor", "editor-2"]


def test_env_and_vkd3d_carried():
    rec = _recipe(bottle=RecipeBottle(runner="wine", arch="win64", vkd3d=True,
                                      env={"DXVK_HUD": "fps"}))
    bottle = materialize.bottle_from_recipe(rec)
    assert bottle.vkd3d is True and bottle.env == {"DXVK_HUD": "fps"}


# ---- CLI (needs YAML to read the recipe file) --------------------------
class _Harness:
    def __init__(self, tmp_path):
        self.out: list[str] = []
        self.err: list[str] = []
        self.calls: list = []
        self.identity_path = str(tmp_path / "identity.json")
        self.store = str(tmp_path / "bottles")
        self.apps = str(tmp_path / "apps")
        self.env = DrydockEnv(
            io=CliIO(out=self.out.append, err=self.err.append),
            store_base=self.store, applications_dir=self.apps,
            run_argv=lambda argv: self.calls.append(argv) or 0,
            identity_path=self.identity_path, icon_theme_dir=str(tmp_path / "icons"))


def _write_recipe(tmp_path, recipe, name="game.recipe") -> str:
    path = tmp_path / name
    path.write_text(recipe_store.dumps(recipe), encoding="utf-8")
    return str(path)


def test_cli_materialize_creates_bottle(tmp_path):
    pytest.importorskip("yaml")
    h = _Harness(tmp_path)
    recipe = _recipe(steps=[])  # no steps → no "not run" note
    path = _write_recipe(tmp_path, recipe)
    assert run_cli(["materialize", path], env=h.env) == 0
    assert bottles.load_bottle("some-game", h.store) is not None
    assert (tmp_path / "apps" / "drydock-some-game-some-game.desktop").exists()
    # the program's identity was wired into the shared map.
    assert identity_store.load(h.identity_path).resolve("game") == "drydock-some-game-some-game"


def test_cli_materialize_reports_unrun_steps(tmp_path):
    pytest.importorskip("yaml")
    from gest.core.drydock.recipe import RecipeStep
    h = _Harness(tmp_path)
    recipe = _recipe(steps=[RecipeStep(action="winetricks", params={"app": "dotnet48"})])
    path = _write_recipe(tmp_path, recipe)
    run_cli(["materialize", path], env=h.env)
    assert any("1 install step(s) not run" in line for line in h.out)


def test_cli_materialize_refuses_existing_without_force(tmp_path):
    pytest.importorskip("yaml")
    h = _Harness(tmp_path)
    path = _write_recipe(tmp_path, _recipe())
    assert run_cli(["materialize", path], env=h.env) == 0
    assert run_cli(["materialize", path], env=h.env) == 1
    assert any("already exists" in e for e in h.err)
    assert run_cli(["materialize", path, "--force"], env=h.env) == 0


def test_cli_materialize_missing_file(tmp_path):
    pytest.importorskip("yaml")
    h = _Harness(tmp_path)
    assert run_cli(["materialize", str(tmp_path / "nope.recipe")], env=h.env) == 1
    assert h.err


def test_recipe_store_round_trip(tmp_path):
    pytest.importorskip("yaml")
    recipe = _recipe()
    text = recipe_store.dumps(recipe)
    restored = recipe_store.loads(text)
    assert restored.to_dict() == recipe.to_dict()
