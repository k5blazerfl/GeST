"""Materialize a ``helm.recipe`` into a manageable Drydock :class:`~.model.Bottle`.

Pure: recipe → a Bottle seeded with its programs, ready for the store and Customs
export. The recipe's install ``steps`` are **not** executed here — that needs the
host-only bottle operations (roadmap phases 4/6). Materialization gives you a
real, listable/launchable bottle now; running the install comes later.
"""

from __future__ import annotations

from gest.core.drydock import bottles
from gest.core.drydock.model import Bottle, Program
from gest.core.drydock.recipe import Recipe


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
