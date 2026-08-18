"""CI-safe tests for recipe → barrel materialization and the `materialize` CLI.

The pure ``barrel_from_recipe`` bridge needs no YAML; the file-based CLI path
reads a helm.recipe, so those tests ``importorskip("yaml")``.
"""

from __future__ import annotations

import pytest

from gest.core.customs import identity_store
from gest.core.drydock import barrels, materialize, recipe_store
from gest.core.drydock.recipe import Recipe, RecipeBarrel, RecipeProgram
from gest.tui.drydock.cli import CliIO, DrydockEnv, run_cli


def _recipe(**over) -> Recipe:
    base = dict(
        app_name="Some Game", app_id="some-game", categories=["Game"],
        barrel=RecipeBarrel(runner="wine", arch="win32", verbs=["dotnet48"], dxvk=True),
        programs=[RecipeProgram(name="Some Game", exe="drive_c/game/game.exe",
                                args=["-w"], category="Game")],
    )
    base.update(over)
    return Recipe(**base)


# ---- pure bridge -------------------------------------------------------
def test_barrel_from_recipe_maps_fields():
    barrel = materialize.barrel_from_recipe(_recipe())
    assert barrel.id == "some-game"
    assert barrel.name == "Some Game"
    assert barrel.runner == "wine" and barrel.arch == "win32"
    assert barrel.verbs == ["dotnet48"] and barrel.dxvk is True
    assert len(barrel.programs) == 1
    prog = barrel.programs[0]
    assert prog.exe == "drive_c/game/game.exe" and prog.args == ["-w"]
    assert prog.category == "Game"


def test_barrel_id_override():
    barrel = materialize.barrel_from_recipe(_recipe(), barrel_id="My Barrel")
    assert barrel.id == "my-barrel"


def test_program_ids_deduped():
    rec = _recipe(programs=[
        RecipeProgram(name="Editor", exe="a.exe"),
        RecipeProgram(name="Editor", exe="b.exe"),  # same name → same base id
    ])
    barrel = materialize.barrel_from_recipe(rec)
    ids = [p.id for p in barrel.programs]
    assert ids == ["editor", "editor-2"]


def test_env_and_vkd3d_carried():
    rec = _recipe(barrel=RecipeBarrel(runner="wine", arch="win64", vkd3d=True,
                                      env={"DXVK_HUD": "fps"}))
    barrel = materialize.barrel_from_recipe(rec)
    assert barrel.vkd3d is True and barrel.env == {"DXVK_HUD": "fps"}


# ---- CLI (needs YAML to read the recipe file) --------------------------
class _Harness:
    def __init__(self, tmp_path):
        self.out: list[str] = []
        self.err: list[str] = []
        self.calls: list = []
        self.identity_path = str(tmp_path / "identity.json")
        self.store = str(tmp_path / "barrels")
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


def test_cli_materialize_creates_barrel(tmp_path):
    pytest.importorskip("yaml")
    h = _Harness(tmp_path)
    recipe = _recipe(steps=[])  # no steps → no "not run" note
    path = _write_recipe(tmp_path, recipe)
    assert run_cli(["materialize", path], env=h.env) == 0
    assert barrels.load_barrel("some-game", h.store) is not None
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


def test_cli_materialize_refuses_recipe_with_lint_errors(tmp_path):
    pytest.importorskip("yaml")
    from gest.core.drydock.recipe import RecipeStep
    h = _Harness(tmp_path)
    # an unknown step action is a lint error; materialize itself ignores steps,
    # so without lint it would silently build a barrel from a broken recipe.
    recipe = _recipe(steps=[RecipeStep(action="frobnicate", params={})])
    path = _write_recipe(tmp_path, recipe)
    assert run_cli(["materialize", path], env=h.env) == 1
    assert barrels.load_barrel("some-game", h.store) is None  # nothing created
    assert any("unknown action" in e for e in h.err)


def test_cli_materialize_no_lint_overrides(tmp_path):
    pytest.importorskip("yaml")
    from gest.core.drydock.recipe import RecipeStep
    h = _Harness(tmp_path)
    recipe = _recipe(steps=[RecipeStep(action="frobnicate", params={})])
    path = _write_recipe(tmp_path, recipe)
    assert run_cli(["materialize", path, "--no-lint"], env=h.env) == 0
    assert barrels.load_barrel("some-game", h.store) is not None
