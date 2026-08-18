"""Materialize a ``helm.recipe`` into a manageable Drydock :class:`~.model.Bottle`.

Pure: recipe → a Bottle seeded with its programs, ready for the store and Customs
export. The recipe's install ``steps`` are **not** executed here — that needs the
host-only bottle operations (roadmap phases 4/6). Materialization gives you a
real, listable/launchable bottle now; running the install comes later.
"""

from __future__ import annotations

from gest.core.drydock import bottles
from gest.core.drydock.model import Bottle, Program
from gest.core.drydock.recipe import Recipe, RecipeBottle, RecipeProgram


def bottle_from_recipe(recipe: Recipe, bottle_id: str = "") -> Bottle:
    """Build a Bottle (and its Programs) from ``recipe``. ``bottle_id`` overrides
    the id derived from the recipe's app name/id."""
    bid = bottles.slug(bottle_id or recipe.app_id or recipe.app_name or "bottle")
    bottle = Bottle(
        id=bid, name=recipe.app_name or bid,
        runner=recipe.bottle.runner, arch=recipe.bottle.arch,
        verbs=list(recipe.bottle.verbs), dxvk=recipe.bottle.dxvk,
        vkd3d=recipe.bottle.vkd3d, env=dict(recipe.bottle.env),
    )
    seen: set[str] = set()
    for program in recipe.programs:
        base = bottles.slug(program.name or program.exe or "app")
        pid, n = base, 2
        while pid in seen:
            pid, n = f"{base}-{n}", n + 1
        seen.add(pid)
        bottle.programs.append(Program(
            id=pid, name=program.name or pid, exe=program.exe,
            args=list(program.args), category=program.category,
        ))
    return bottle


def recipe_from_bottle(bottle: Bottle) -> Recipe:
    """The inverse of :func:`bottle_from_recipe`: capture a configured bottle as a
    shareable recipe. This records the bottle *config* + programs — not the install
    ``steps`` (those aren't kept on a bottle), so a materialize→export round-trip
    preserves the runner/arch/verbs and programs, and leaves ``steps`` empty."""
    category = "Game" if any(p.category == "Game" for p in bottle.programs) else "Application"
    return Recipe(
        app_name=bottle.name or bottle.id, app_id=bottle.id, categories=[category],
        bottle=RecipeBottle(runner=bottle.runner, arch=bottle.arch,
                            verbs=list(bottle.verbs), dxvk=bottle.dxvk,
                            vkd3d=bottle.vkd3d, env=dict(bottle.env)),
        programs=[RecipeProgram(name=p.name, exe=p.exe, args=list(p.args),
                                category=p.category) for p in bottle.programs],
        steps=[], files=[], prereqs="auto",
    )
