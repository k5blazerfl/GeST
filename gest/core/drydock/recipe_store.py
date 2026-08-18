"""Read/write a ``helm.recipe`` file (YAML).

The recipe *model* (:mod:`.recipe`) is dict-pure; this is the thin YAML edge, so
the parser dependency stays optional. Lazy PyYAML — an import-only dependency,
never added to core deps (same discipline as the Lutris importer).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from gest.core.drydock.recipe import Recipe


def loads(text: str) -> Recipe:
    data = _yaml().safe_load(text)
    if not isinstance(data, Mapping):
        raise ValueError("not a helm.recipe (expected a YAML mapping)")
    return Recipe.from_dict(data)


def dumps(recipe: Recipe) -> str:
    return _yaml().safe_dump(recipe.to_dict(), sort_keys=False, default_flow_style=False)


def load(path: str) -> Recipe:
    return loads(Path(path).expanduser().read_text(encoding="utf-8"))


def save(recipe: Recipe, path: str) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dumps(recipe), encoding="utf-8")
    return target


def _yaml():
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - trivial guard
        raise RuntimeError(
            "helm.recipe I/O needs PyYAML — install dev-python/pyyaml (pip install pyyaml)"
        ) from exc
    return yaml
