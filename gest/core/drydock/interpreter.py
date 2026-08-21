"""Compile a ``helm.recipe`` into an ordered **plan** of concrete operations.

This is the install-time sibling of :mod:`.launch`'s ``(env, argv)`` builder: the
plan is fully computed and unit-testable here; a host executor (which needs real
Wine and touches the filesystem) runs it later — running the plan is *not* part of
this module. Roadmap phase 6.

Each :class:`PlannedOp` is either a ``command`` (argv + env for the executor to
spawn), a filesystem op (``extract``/``move``/``copy``/``chmodx``/``write``), or a
``manual`` step the executor must surface to the user rather than fake. Recipe
variables (``$GAMEDIR``, ``$WINEPREFIX``, ``$CACHE``) and file-id references are
resolved against a :class:`PlanContext`.

Scope: the command steps are planned for both **wine** barrels (``wine`` +
``winetricks`` + ``wineserver``) and **Proton** barrels, where they route through
``umu-run`` (Proton's universal launcher — it bundles DXVK/VKD3D + protonfixes and
creates the prefix). Filesystem steps are runner-agnostic. Only genuinely
un-runnable directives stay ``manual``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from gest.core.drydock import recipe as R
from gest.core.drydock.model import RUNNER_PROTON
from gest.core.drydock.recipe import Recipe

# The Proton launcher and the env it needs (mirrors launch.build_env's Proton
# branch). ``GAMEID`` is mandatory for umu; ``umu-0`` is the generic "no
# protonfix" id used for install-time steps. ``STORE=none`` = not a store title.
UMU_RUN = "umu-run"
UMU_GAMEID = "umu-0"
UMU_STORE = "none"

OP_COMMAND = "command"
OP_EXTRACT = "extract"
OP_MOVE = "move"
OP_COPY = "copy"
OP_CHMODX = "chmodx"
OP_WRITE = "write"
OP_MANUAL = "manual"

_VAR = re.compile(r"\$\{(\w+)\}|\$(\w+)")


@dataclass(slots=True)
class PlanContext:
    """The concrete paths a recipe's variables resolve against."""

    prefix: str  # $WINEPREFIX
    gamedir: str  # $GAMEDIR — the install root
    cache: str = ""  # $CACHE — where `files` are downloaded
    arch: str = "win64"
    runner: str = "wine"
    runner_version: str = ""  # Proton build → PROTONPATH (empty → umu's default)

    def variables(self) -> dict[str, str]:
        return {"GAMEDIR": self.gamedir, "WINEPREFIX": self.prefix,
                "PREFIX": self.prefix, "CACHE": self.cache}


@dataclass(slots=True)
class PlannedOp:
    kind: str
    summary: str
    argv: list[str] = field(default_factory=list)  # kind == OP_COMMAND
    env: dict[str, str] = field(default_factory=dict)
    detail: dict = field(default_factory=dict)  # kind-specific (src/dst/path/…)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "summary": self.summary,
                "argv": list(self.argv), "env": dict(self.env), "detail": dict(self.detail)}


def plan(recipe: Recipe, context: PlanContext) -> list[PlannedOp]:
    """Compile ``recipe.steps`` into an ordered list of :class:`PlannedOp`."""
    variables = dict(context.variables())
    file_vars = _file_vars(recipe, context.cache)
    return [_plan_step(step, context, variables, file_vars) for step in recipe.steps]


def _file_vars(recipe: Recipe, cache: str) -> dict[str, str]:
    """Map each ``files`` id to its on-disk path in the cache (so an ``extract``
    that names a file id resolves to the downloaded artifact)."""
    out: dict[str, str] = {}
    for f in recipe.files:
        name = f.filename or (f.url.rsplit("/", 1)[-1] if f.url else "") or f.id
        out[f.id] = str(Path(cache) / name) if cache else name
    return out


def _subst(value: str, variables: dict[str, str]) -> str:
    def repl(match: re.Match) -> str:
        name = match.group(1) or match.group(2)
        return variables.get(name, match.group(0))
    return _VAR.sub(repl, value)


def _s(params: dict, key: str, variables: dict, default: str = "") -> str:
    return _subst(str(params.get(key, default)), variables)


def _wine_env(context: PlanContext) -> dict[str, str]:
    return {"WINEPREFIX": context.prefix, "WINEARCH": context.arch}


def _verbs(params: dict) -> list[str]:
    raw = params.get("app", params.get("apps", params.get("value")))
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(v) for v in raw]
    return str(raw).split()


def _plan_step(step: R.RecipeStep, context: PlanContext,
               variables: dict, file_vars: dict) -> PlannedOp:
    action, params = step.action, step.params

    # --- filesystem ops (runner-agnostic) ---
    if action == R.ACTION_EXTRACT:
        src = file_vars.get(str(params.get("file", "")), _s(params, "file", variables))
        dst = _s(params, "dst", variables) or context.gamedir
        return PlannedOp(OP_EXTRACT, f"extract {src} → {dst}", detail={"src": src, "dst": dst})
    if action in (R.ACTION_MOVE, R.ACTION_COPY):
        src = file_vars.get(str(params.get("src", "")), _s(params, "src", variables))
        dst = _s(params, "dst", variables)
        kind = OP_MOVE if action == R.ACTION_MOVE else OP_COPY
        return PlannedOp(kind, f"{action} {src} → {dst}", detail={"src": src, "dst": dst})
    if action == R.ACTION_CHMODX:
        path = _s(params, "file", variables) or _s(params, "path", variables)
        return PlannedOp(OP_CHMODX, f"chmod +x {path}", detail={"path": path})
    if action in (R.ACTION_WRITE_FILE, R.ACTION_WRITE_CONFIG, R.ACTION_WRITE_JSON):
        path = _s(params, "file", variables) or _s(params, "path", variables)
        fmt = {"write_file": "file", "write_config": "config", "write_json": "json"}[action]
        return PlannedOp(OP_WRITE, f"write {fmt} {path}",
                         detail={"path": path, "format": fmt, "params": dict(params)})

    # --- command ops: wine directly, Proton via umu-run ---
    if action in (R.ACTION_CREATE_PREFIX, R.ACTION_WINEEXEC, R.ACTION_WINETRICKS,
                  R.ACTION_REGEDIT_FILE, R.ACTION_WINEKILL):
        if context.runner == RUNNER_PROTON:
            return _plan_proton_command(action, params, context, variables)
        return _plan_wine_command(action, params, context, variables)

    # --- ACTION_MANUAL and anything unmapped ---
    return PlannedOp(OP_MANUAL, f"manual: {params.get('original', action)}",
                     detail={"original": params.get("original", action), "params": dict(params)})


def _plan_wine_command(action: str, params: dict, context: PlanContext,
                       variables: dict) -> PlannedOp:
    env = _wine_env(context)
    if action == R.ACTION_CREATE_PREFIX:
        return PlannedOp(OP_COMMAND, f"create {context.arch} prefix at {context.prefix}",
                         argv=["wineboot", "-i"], env=env)
    if action == R.ACTION_WINETRICKS:
        verbs = _verbs(params)
        return PlannedOp(OP_COMMAND, f"winetricks {' '.join(verbs)}",
                         argv=["winetricks", "-q", *verbs], env=env)
    if action == R.ACTION_WINEEXEC:
        exe = _s(params, "executable", variables) or _s(params, "exe", variables)
        args = [_subst(str(a), variables) for a in params.get("args", [])] \
            if isinstance(params.get("args"), (list, tuple)) \
            else (_s(params, "args", variables).split() if params.get("args") else [])
        return PlannedOp(OP_COMMAND, f"wine {exe} {' '.join(args)}".strip(),
                         argv=["wine", exe, *args], env=env)
    if action == R.ACTION_REGEDIT_FILE:
        reg = _s(params, "file", variables) or _s(params, "path", variables)
        return PlannedOp(OP_COMMAND, f"wine regedit {reg}",
                         argv=["wine", "regedit", reg], env=env)
    # ACTION_WINEKILL
    return PlannedOp(OP_COMMAND, "kill the prefix's wine processes",
                     argv=["wineserver", "-k"], env=env)


def _umu_env(context: PlanContext) -> dict[str, str]:
    """The umu-run environment for a Proton install step (see :mod:`.launch`)."""
    env = {"WINEPREFIX": context.prefix, "GAMEID": UMU_GAMEID, "STORE": UMU_STORE}
    if context.runner_version:
        env["PROTONPATH"] = context.runner_version  # else umu picks its default Proton
    return env


def _plan_proton_command(action: str, params: dict, context: PlanContext,
                         variables: dict) -> PlannedOp:
    """The Proton sibling of :func:`_plan_wine_command`: the same recipe verbs, run
    through ``umu-run`` (which sets up Proton's wine + prefix). umu forwards its
    argument to ``proton run``, so wine built-ins (``regedit``/``wineserver``) and
    ``winetricks`` reach the Proton prefix; ``createprefix`` is umu's own verb."""
    env = _umu_env(context)
    if action == R.ACTION_CREATE_PREFIX:
        return PlannedOp(OP_COMMAND,
                         f"umu createprefix ({context.arch} Proton) at {context.prefix}",
                         argv=[UMU_RUN, "createprefix"], env=env)
    if action == R.ACTION_WINETRICKS:
        verbs = _verbs(params)
        return PlannedOp(OP_COMMAND, f"umu winetricks {' '.join(verbs)}".strip(),
                         argv=[UMU_RUN, "winetricks", "-q", *verbs], env=env)
    if action == R.ACTION_WINEEXEC:
        exe = _s(params, "executable", variables) or _s(params, "exe", variables)
        args = [_subst(str(a), variables) for a in params.get("args", [])] \
            if isinstance(params.get("args"), (list, tuple)) \
            else (_s(params, "args", variables).split() if params.get("args") else [])
        return PlannedOp(OP_COMMAND, f"umu-run {exe} {' '.join(args)}".strip(),
                         argv=[UMU_RUN, exe, *args], env=env)
    if action == R.ACTION_REGEDIT_FILE:
        reg = _s(params, "file", variables) or _s(params, "path", variables)
        return PlannedOp(OP_COMMAND, f"umu regedit {reg}",
                         argv=[UMU_RUN, "regedit", reg], env=env)
    # ACTION_WINEKILL
    return PlannedOp(OP_COMMAND, "kill the Proton prefix's wine processes",
                     argv=[UMU_RUN, "wineserver", "-k"], env=env)
