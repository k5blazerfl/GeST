"""Import a Lutris install script into a Drydock ``helm.recipe`` (one-way).

Roadmap phase 7 / ``docs/design/drydock-lutris-interop.md``. This is an *interop
bridge*, not a fork: we read Lutris's YAML and emit **our own** recipe format,
mapping the Wine/Proton subset faithfully and being honest about the rest —

* **native**  — a 1:1 Drydock step (or bottle state);
* **flag**    — recognised but not executable → kept as a visible ``manual`` step
  + a warning, never silently faked;
* **reject**  — out of Drydock's scope (e.g. a non-Wine runner) → dropped, noted.

:func:`convert` takes an **already-parsed dict**, so it is pure and fully
CI-testable with no YAML dependency. :func:`load_script` / :func:`dump_recipe`
are thin edges that lazily import PyYAML (an optional, import-only dependency).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from gest.core.drydock import recipe as R
from gest.core.drydock.model import ARCH_WIN32, ARCH_WIN64, RUNNER_WINE

# Lutris runners we can convert. Proton, in Lutris, is a *wine version* — still
# the "wine" runner — so this one value covers both plain Wine and Proton.
_WINE_RUNNERS = frozenset({"wine"})

# installer directives with a 1:1 native step.
_NATIVE_DIRECTIVES = {
    "extract": R.ACTION_EXTRACT,
    "move": R.ACTION_MOVE,
    "copy": R.ACTION_COPY,
    "merge": R.ACTION_COPY,  # merge ≈ copy in our vocabulary
    "chmodx": R.ACTION_CHMODX,
    "execute": R.ACTION_EXECUTE,
    "write_file": R.ACTION_WRITE_FILE,
    "write_config": R.ACTION_WRITE_CONFIG,
    "write_json": R.ACTION_WRITE_JSON,
}

# wine ``task:`` subtasks with a native step.
_NATIVE_TASKS = {
    "create_prefix": R.ACTION_CREATE_PREFIX,
    "wineexec": R.ACTION_WINEEXEC,
    "winetricks": R.ACTION_WINETRICKS,
    "set_regedit": R.ACTION_REGEDIT,
    "set_regedit_file": R.ACTION_REGEDIT_FILE,
    "delete_registry_key": R.ACTION_REGDELETE,
    "winekill": R.ACTION_WINEKILL,
    "eject_disc": R.ACTION_EJECT_DISC,
}

# recognised but not executable → a visible manual TODO.
_FLAG_DIRECTIVES = frozenset({"input_menu", "insert-disc"})
_FLAG_TASKS = frozenset({"gogdl_setup"})  # store integration, out of scope for v1

# tasks that belong to another runner → rejected outright.
_REJECT_TASKS = frozenset({"dosexec"})


@dataclass(slots=True)
class ImportResult:
    """The outcome of a conversion. ``recipe`` is ``None`` only when the whole
    script was rejected (e.g. a non-Wine runner)."""

    recipe: R.Recipe | None
    warnings: list[str] = field(default_factory=list)  # flagged / partial mappings
    rejected: list[str] = field(default_factory=list)  # out-of-scope, dropped

    @property
    def ok(self) -> bool:
        return self.recipe is not None

    @property
    def manual_steps(self) -> int:
        if self.recipe is None:
            return 0
        return sum(1 for s in self.recipe.steps if s.action == R.ACTION_MANUAL)


def convert(script: Mapping) -> ImportResult:
    """Convert a (flattened) Lutris install script dict to a Drydock recipe."""
    warnings: list[str] = []
    rejected: list[str] = []

    runner = str(script.get("runner", "")).strip().lower()
    if runner and runner not in _WINE_RUNNERS:
        return ImportResult(
            recipe=None,
            rejected=[f"unsupported Lutris runner {runner!r}: Drydock is Wine/Proton only"],
        )

    wine_cfg = _as_mapping(script.get("wine"))
    arch = ARCH_WIN32 if str(wine_cfg.get("arch", "")).lower() == "win32" else ARCH_WIN64
    bottle = R.RecipeBottle(runner=RUNNER_WINE, arch=arch,
                            dxvk=_as_bool(wine_cfg.get("dxvk")),
                            vkd3d=_as_bool(wine_cfg.get("vkd3d")))

    # system.env → bottle env; everything else under system.* is HeDE's job.
    system = _as_mapping(script.get("system"))
    bottle.env = {str(k): str(v) for k, v in _as_mapping(system.get("env")).items()}
    for key in system:
        if key != "env":
            warnings.append(f"system:{key} not mapped — the HeDE session owns it")

    files = [_convert_file(entry, warnings) for entry in _as_list_of(script.get("files"))]

    steps: list[R.RecipeStep] = []
    for directive in _as_list_of(script.get("installer")):
        _convert_directive(directive, steps, bottle, warnings, rejected)

    game = _as_mapping(script.get("game"))
    app_name = str(script.get("name") or script.get("game_slug")
                   or script.get("slug") or "app")
    programs: list[R.RecipeProgram] = []
    if game.get("exe"):
        programs.append(R.RecipeProgram(name=app_name, exe=str(game["exe"]),
                                        args=_as_args(game.get("args")), category="Game"))
    else:
        warnings.append("no game.exe — recipe has no launchable program yet")

    recipe = R.Recipe(
        app_name=app_name,
        app_id=str(script.get("game_slug") or script.get("slug") or ""),
        categories=["Game"], bottle=bottle, files=files, steps=steps,
        programs=programs, prereqs="auto",
    )
    return ImportResult(recipe=recipe, warnings=warnings, rejected=rejected)


def _convert_directive(directive, steps, bottle, warnings, rejected) -> None:
    if not isinstance(directive, Mapping) or len(directive) != 1:
        warnings.append(f"skipped malformed installer directive: {directive!r}")
        return
    (name, raw), = directive.items()
    name = str(name)
    params = dict(raw) if isinstance(raw, Mapping) else {"value": raw}

    if name in _NATIVE_DIRECTIVES:
        steps.append(R.RecipeStep(action=_NATIVE_DIRECTIVES[name], params=params))
    elif name == "task":
        _convert_task(params, steps, bottle, warnings, rejected)
    elif name in _FLAG_DIRECTIVES:
        warnings.append(f"installer directive {name!r} is interactive — left as a manual TODO")
        steps.append(R.RecipeStep(R.ACTION_MANUAL, {"original": name, "params": params}))
    else:
        warnings.append(f"unknown installer directive {name!r} — left as a manual TODO")
        steps.append(R.RecipeStep(R.ACTION_MANUAL, {"original": name, "params": params}))


def _convert_task(params, steps, bottle, warnings, rejected) -> None:
    task = str(params.get("name", "")).strip()
    rest = {k: v for k, v in params.items() if k != "name"}

    if task in _NATIVE_TASKS:
        steps.append(R.RecipeStep(action=_NATIVE_TASKS[task], params=rest))
        if task == "winetricks":
            verbs = rest.get("app", rest.get("apps", rest.get("value")))
            for verb in _as_list(verbs):
                if verb not in bottle.verbs:
                    bottle.verbs.append(verb)
    elif task in _REJECT_TASKS:
        rejected.append(f"task {task!r} is not a Wine task — dropped")
    elif task in _FLAG_TASKS:
        warnings.append(f"task {task!r} (store integration) unsupported — left as a manual TODO")
        steps.append(R.RecipeStep(R.ACTION_MANUAL, {"original": f"task:{task}", "params": rest}))
    else:
        warnings.append(f"unknown task {task!r} — left as a manual TODO")
        steps.append(R.RecipeStep(R.ACTION_MANUAL, {"original": f"task:{task}", "params": rest}))


def _convert_file(entry, warnings) -> R.RecipeFile:
    if not isinstance(entry, Mapping) or len(entry) != 1:
        warnings.append(f"skipped malformed files entry: {entry!r}")
        return R.RecipeFile(id="unknown")
    (fid, val), = entry.items()
    fid = str(fid)
    if isinstance(val, Mapping):
        return R.RecipeFile(id=fid, url=str(val.get("url", "")),
                            filename=str(val.get("filename", "")))
    text = str(val)
    if text.startswith("N/A"):
        reason = text[3:].lstrip(": ").strip()
        return R.RecipeFile(id=fid, user_provided=reason or "provide this file")
    if text.startswith("$STEAM"):
        warnings.append(f"file {fid!r} is a Steam reference ({text}) — must be provided manually")
        return R.RecipeFile(id=fid, user_provided=f"Steam data: {text}")
    return R.RecipeFile(id=fid, url=text)


# --- small coercion helpers (Lutris YAML is loosely typed) ------------------

def _as_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"true", "1", "yes", "on"}
    return bool(v)


def _as_args(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return v.split()
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [str(v)]


def _as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [str(v)]


def _as_list_of(v) -> list:
    return list(v) if isinstance(v, (list, tuple)) else []


def _as_mapping(v) -> dict:
    return dict(v) if isinstance(v, Mapping) else {}


# --- YAML edges (lazy PyYAML — the only place the parser is needed) ----------

def load_script(text: str) -> dict:
    """Parse a Lutris install script (YAML) into a flattened dict `convert`
    understands. Lutris website exports nest the body under ``script:`` with
    metadata (name/runner/…) at the top level — this merges the two."""
    data = _yaml().safe_load(text)
    if not isinstance(data, Mapping):
        raise ValueError("not a Lutris install script (expected a YAML mapping)")
    data = dict(data)
    inner = data.get("script")
    if isinstance(inner, Mapping):
        merged = dict(inner)
        for key in ("name", "game_slug", "slug", "version", "runner", "description"):
            if key in data and key not in merged:
                merged[key] = data[key]
        return merged
    return data


def dump_recipe(recipe: R.Recipe) -> str:
    """Serialize a recipe to ``helm.recipe`` YAML."""
    return _yaml().safe_dump(recipe.to_dict(), sort_keys=False, default_flow_style=False)


def _yaml():
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - trivial guard
        raise RuntimeError(
            "import-lutris needs PyYAML — install dev-python/pyyaml (pip install pyyaml)"
        ) from exc
    return yaml
