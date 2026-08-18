"""CI-safe tests for `drydock install-recipe` — materialize + install in one, with
the install running against the bottle's own (pinned) prefix."""

from __future__ import annotations

import pytest

from gest.core.drydock import bottles


def _recipe_text():
    from gest.core.drydock import recipe_store
    from gest.core.drydock.recipe import (
        Recipe,
        RecipeBottle,
        RecipeProgram,
        RecipeStep,
    )
    recipe = Recipe(
        app_name="Some Game", app_id="some-game",
        bottle=RecipeBottle(runner="wine", arch="win64"),
        programs=[RecipeProgram(name="Some Game", exe="drive_c/game/game.exe")],
        steps=[RecipeStep("create_prefix", {"arch": "win64"}),
               RecipeStep("winetricks", {"app": "dotnet48"})])
    return recipe_store.dumps(recipe)


class _H:
    def __init__(self, tmp_path):
        from gest.tui.drydock.cli import CliIO, DrydockEnv
        self.out: list[str] = []
        self.err: list[str] = []
        self.ran: list = []
        self.store = str(tmp_path / "bottles")
        self.env = DrydockEnv(
            io=CliIO(out=self.out.append, err=self.err.append),
            store_base=self.store, applications_dir=str(tmp_path / "apps"),
            identity_path=str(tmp_path / "id.json"), icon_theme_dir=str(tmp_path / "ic"),
            run_argv=lambda a: 0, step_runner=lambda op: self.ran.append(op) or 0)


def _write(tmp_path):
    pytest.importorskip("yaml")
    path = tmp_path / "game.recipe"
    path.write_text(_recipe_text(), encoding="utf-8")
    return str(path)


def test_install_recipe_creates_bottle_and_runs_install(tmp_path):
    from gest.tui.drydock.cli import run_cli
    h = _H(tmp_path)
    assert run_cli(["install-recipe", _write(tmp_path), "--run"], env=h.env) == 0
    bottle = bottles.load_bottle("some-game", h.store)
    assert bottle is not None
    # the install steps actually executed (create_prefix + winetricks)
    assert len(h.ran) == 2


def test_install_runs_against_the_bottles_pinned_prefix(tmp_path):
    from gest.tui.drydock.cli import run_cli
    h = _H(tmp_path)
    run_cli(["install-recipe", _write(tmp_path), "--run"], env=h.env)
    bottle = bottles.load_bottle("some-game", h.store)
    # every command op's WINEPREFIX is the bottle's own prefix — the seam is closed.
    prefixes = {op.env.get("WINEPREFIX") for op in h.ran if op.env}
    assert prefixes == {bottle.prefix}
    assert bottle.prefix.endswith("/some-game/prefix")


def test_dry_run_does_not_execute(tmp_path):
    from gest.tui.drydock.cli import run_cli
    h = _H(tmp_path)
    assert run_cli(["install-recipe", _write(tmp_path)], env=h.env) == 0
    assert h.ran == []  # nothing executed
    assert any("dry run" in line for line in h.out)
    # but the bottle was still created (materialize half always runs)
    assert bottles.load_bottle("some-game", h.store) is not None


def test_refuses_lint_errors(tmp_path):
    from gest.core.drydock import recipe_store
    from gest.core.drydock.recipe import Recipe, RecipeBottle, RecipeStep
    from gest.tui.drydock.cli import run_cli
    h = _H(tmp_path)
    bad = tmp_path / "bad.recipe"
    bad.write_text(recipe_store.dumps(Recipe(
        app_name="X", app_id="x", bottle=RecipeBottle(runner="wine", arch="win64"),
        steps=[RecipeStep("frobnicate", {})])), encoding="utf-8")
    assert run_cli(["install-recipe", str(bad), "--run"], env=h.env) == 1
    assert bottles.load_bottle("x", h.store) is None and h.ran == []


def test_refuses_existing_without_force(tmp_path):
    from gest.tui.drydock.cli import run_cli
    h = _H(tmp_path)
    recipe = _write(tmp_path)
    assert run_cli(["install-recipe", recipe], env=h.env) == 0
    assert run_cli(["install-recipe", recipe], env=h.env) == 1
    assert run_cli(["install-recipe", recipe, "--force"], env=h.env) == 0
