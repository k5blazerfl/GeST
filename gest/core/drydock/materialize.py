"""Materialize a ``helm.recipe`` into a manageable Drydock :class:`~.model.Barrel`.

Pure: recipe → a Barrel seeded with its programs, ready for the store and Customs
export. The recipe's install ``steps`` are **not** executed here — that needs the
host-only barrel operations (roadmap phases 4/6). Materialization gives you a
real, listable/launchable barrel now; running the install comes later.
"""

from __future__ import annotations

from gest.core.drydock import barrels
from gest.core.drydock.model import Barrel, Program
from gest.core.drydock.recipe import Recipe, RecipeBarrel, RecipeProgram


def barrel_from_recipe(recipe: Recipe, barrel_id: str = "") -> Barrel:
    """Build a Barrel (and its Programs) from ``recipe``. ``barrel_id`` overrides
    the id derived from the recipe's app name/id."""
    bid = barrels.slug(barrel_id or recipe.app_id or recipe.app_name or "barrel")
    barrel = Barrel(
        id=bid, name=recipe.app_name or bid,
        runner=recipe.barrel.runner, arch=recipe.barrel.arch,
        verbs=list(recipe.barrel.verbs), dxvk=recipe.barrel.dxvk,
        vkd3d=recipe.barrel.vkd3d, env=dict(recipe.barrel.env),
    )
    seen: set[str] = set()
    for program in recipe.programs:
        base = barrels.slug(program.name or program.exe or "app")
        pid, n = base, 2
        while pid in seen:
            pid, n = f"{base}-{n}", n + 1
        seen.add(pid)
        barrel.programs.append(Program(
            id=pid, name=program.name or pid, exe=program.exe,
            args=list(program.args), category=program.category,
        ))
    return barrel


def recipe_from_barrel(barrel: Barrel) -> Recipe:
    """The inverse of :func:`barrel_from_recipe`: capture a configured barrel as a
    shareable recipe. This records the barrel *config* + programs — not the install
    ``steps`` (those aren't kept on a barrel), so a materialize→export round-trip
    preserves the runner/arch/verbs and programs, and leaves ``steps`` empty."""
    category = "Game" if any(p.category == "Game" for p in barrel.programs) else "Application"
    return Recipe(
        app_name=barrel.name or barrel.id, app_id=barrel.id, categories=[category],
        barrel=RecipeBarrel(runner=barrel.runner, arch=barrel.arch,
                            verbs=list(barrel.verbs), dxvk=barrel.dxvk,
                            vkd3d=barrel.vkd3d, env=dict(barrel.env)),
        programs=[RecipeProgram(name=p.name, exe=p.exe, args=list(p.args),
                                category=p.category) for p in barrel.programs],
        steps=[], files=[], prereqs="auto",
    )
