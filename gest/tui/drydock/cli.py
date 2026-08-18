"""``drydock`` — manage Wine/Proton barrels and launch Windows apps.

Pure, TTY-free command layer: each ``cmd_*`` takes parsed args + an injectable
:class:`DrydockEnv` and returns an exit code. ``drydock-run <barrel> <program>``
is the stub the synthesized ``.desktop`` Exec points at.

    drydock create office --runner wine --arch win32
    drydock register office /prefix/excel.exe --name Excel --gamescope --fsr
    drydock scan office            # adopt wine's auto-generated launchers
    drydock winetricks office dotnet48 corefonts   # install DLLs/runtimes
    drydock winecfg office         # configure the prefix; kill/shell/doctor too
    drydock materialize game.recipe   # create a barrel from a helm.recipe
    drydock plan game.recipe          # show the compiled install plan (dry run)
    drydock install-recipe game.recipe --run   # create the barrel AND run its install
    drydock prereqs office
    drydock run office excel
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from gest.core.customs import icons, identity_store, mime
from gest.core.customs.desktop import remove_entry, write_entry
from gest.core.drydock import barrels, desktop, launch, prereq
from gest.core.drydock.model import ARCHES, RUNNERS, Barrel, GraphicsProfile, Program


@dataclass
class CliIO:
    out: Callable[[str], None]
    err: Callable[[str], None]


def _default_io() -> CliIO:
    return CliIO(out=print, err=lambda s: print(s, file=sys.stderr))


def _default_run(argv: list[str]) -> int:
    """Run a host tool (wrestool/icotool/xdg-mime/…) and return its exit code.
    Best-effort — the caller decides whether a nonzero code matters."""
    try:
        return subprocess.run(argv).returncode
    except FileNotFoundError:
        return 127


def _default_tool_spawn(argv: list[str], env: dict[str, str]) -> int:
    """Spawn a maintenance tool (winetricks/winecfg/shell/…) with extra env,
    inheriting the terminal. Host-only."""
    try:
        return subprocess.run(argv, env={**os.environ, **env}).returncode
    except FileNotFoundError:
        return 127


@dataclass
class DrydockEnv:
    io: CliIO = field(default_factory=_default_io)
    store_base: str = barrels.DRYDOCK_DIR
    applications_dir: str = "~/.local/share/applications"
    wine_apps_dir: str = desktop.WINE_APPS_DIR
    launch_fn: Callable = launch.launch
    # Customs spine (host tools + the shared identity map) — injectable so the
    # command layer stays CI-safe. identity_path/icon_theme_dir empty → defaults.
    run_argv: Callable[[list[str]], int] = _default_run
    identity_path: str = ""
    icon_theme_dir: str = icons.ICON_THEME_DIR
    # Runs one install-plan op (0 == ok); None → the host runner. Injectable so
    # `install` is testable without spawning wine / touching the filesystem.
    step_runner: Callable | None = None
    # Maintenance-verb spawn (argv, env) and the tool-presence probe for `doctor`
    # — injectable so winetricks/winecfg/shell/kill/doctor stay CI-safe.
    tool_spawn: Callable[[list[str], dict[str, str]], int] = _default_tool_spawn
    which: Callable[[str], str | None] = shutil.which


def _load(env: DrydockEnv, barrel_id: str) -> Barrel | None:
    barrel = barrels.load_barrel(barrel_id, env.store_base)
    if barrel is None:
        env.io.err(f"no such barrel {barrel_id!r}")
    return barrel


def _write_launcher(env: DrydockEnv, barrel: Barrel, program: Program) -> str:
    path = write_entry(desktop.desktop_entry(barrel, program),
                       desktop.desktop_id(barrel.id, program.id), env.applications_dir)
    return str(path)


def _upsert_program(barrel: Barrel, program: Program) -> None:
    barrel.programs = [p for p in barrel.programs if p.id != program.id]
    barrel.programs.append(program)


def _identity_path(env: DrydockEnv) -> str | None:
    return env.identity_path or None


def _wire_customs(env: DrydockEnv, barrel: Barrel, program: Program) -> None:
    """Make a synthesized launcher a first-class HeDE citizen: extract its icon,
    register its taskbar identity, and set it as the default handler for its MIME
    types. The DB refresh is left to :func:`_refresh_db` so a batch (scan) does it
    once. Host tools run through ``env.run_argv``; failures are non-fatal."""
    did = desktop.desktop_id(barrel.id, program.id)

    # 1. Icon: wrestool extracts the .exe's group-icon → icotool renders a PNG
    #    into the hicolor theme under the launcher's Icon name (<desktop_id>).
    exe = desktop.local_exe_path(barrel, program)
    if exe:
        png = icons.icon_install_path(did, theme_dir=env.icon_theme_dir)
        png.parent.mkdir(parents=True, exist_ok=True)
        ico = png.with_suffix(".ico")
        if env.run_argv(icons.extract_argv(exe, str(ico))) == 0:
            env.run_argv(icons.convert_argv(str(ico), str(png)))
        with contextlib.suppress(OSError):
            ico.unlink()

    # 2. Identity: the WM_CLASS the window will present → this launcher, so the
    #    taskbar resolves it (the source of truth HeDE reads).
    wm_class = desktop.default_wm_class(program)
    if wm_class:
        identity_store.register_entry([wm_class], did, _identity_path(env))

    # 3. MIME: make this launcher the default handler for .exe/.msi/.lnk/.bat.
    env.run_argv(mime.register_default_argv(did, mime.DRYDOCK_TYPES))


def _refresh_db(env: DrydockEnv) -> None:
    env.run_argv(mime.update_database_argv(env.applications_dir))


def cmd_create(args, env: DrydockEnv) -> int:
    barrel = Barrel(id=barrels.slug(args.name), name=args.name, runner=args.runner,
                    runner_version=args.version, arch=args.arch,
                    dxvk=args.dxvk, vkd3d=args.vkd3d)
    if not barrel.is_valid():
        env.io.err("invalid barrel (check --runner and --arch)")
        return 2
    path = barrels.save_barrel(barrel, env.store_base)
    env.io.out(f"created barrel {barrel.id} ({path})")
    return 0


def cmd_list(args, env: DrydockEnv) -> int:
    for bid in barrels.list_barrels(env.store_base):
        env.io.out(bid)
    return 0


def cmd_show(args, env: DrydockEnv) -> int:
    barrel = _load(env, args.barrel)
    if barrel is None:
        return 1
    runner = f"{barrel.runner}" + (f" {barrel.runner_version}" if barrel.runner_version else "")
    env.io.out(f"{barrel.name} [{barrel.id}]  runner={runner}  arch={barrel.arch}")
    env.io.out(f"prefix: {barrel.prefix}")
    for program in barrel.programs:
        env.io.out(f"  - {program.id}: {program.name}  ({program.exe})")
    return 0


def cmd_rm(args, env: DrydockEnv) -> int:
    barrel = barrels.load_barrel(args.barrel, env.store_base)
    if barrel is not None:
        for program in barrel.programs:
            did = desktop.desktop_id(barrel.id, program.id)
            remove_entry(did, env.applications_dir)
            identity_store.unregister_entry(did, _identity_path(env))
            with contextlib.suppress(OSError):
                icons.icon_install_path(did, theme_dir=env.icon_theme_dir).unlink()
        if barrel.programs:
            _refresh_db(env)
    if barrels.delete_barrel(args.barrel, env.store_base):
        env.io.out(f"removed barrel {args.barrel}")
        return 0
    env.io.err(f"no such barrel {args.barrel!r}")
    return 1


def _graphics_from_args(args) -> GraphicsProfile:
    return GraphicsProfile(gamescope=args.gamescope, fsr=args.fsr, hdr=args.hdr,
                           gamemode=args.gamemode, mangohud=args.mangohud)


def cmd_register(args, env: DrydockEnv) -> int:
    barrel = _load(env, args.barrel)
    if barrel is None:
        return 1
    program = Program(id=barrels.slug(args.name), name=args.name, exe=args.exe,
                      category="Game" if args.game else "Application",
                      graphics=_graphics_from_args(args))
    _upsert_program(barrel, program)
    barrels.save_barrel(barrel, env.store_base)
    launcher = _write_launcher(env, barrel, program)
    _wire_customs(env, barrel, program)
    _refresh_db(env)
    env.io.out(f"registered {program.id}; launcher {launcher} (icon + identity + MIME wired)")
    return 0


def cmd_scan(args, env: DrydockEnv) -> int:
    barrel = _load(env, args.barrel)
    if barrel is None:
        return 1
    wine_dir = args.wine_apps_dir or env.wine_apps_dir
    count = 0
    for entry in desktop.harvest_dir(wine_dir):
        program = desktop.program_from_harvested(entry, barrels.slug(entry.name or "app"))
        _upsert_program(barrel, program)
        _write_launcher(env, barrel, program)
        _wire_customs(env, barrel, program)
        env.io.out(f"adopted {program.name} ({program.exe})")
        count += 1
    barrels.save_barrel(barrel, env.store_base)
    if count:
        _refresh_db(env)
    env.io.out(f"{count} app(s) adopted")
    return 0


def cmd_prereqs(args, env: DrydockEnv) -> int:
    barrel = _load(env, args.barrel)
    if barrel is None:
        return 1
    for req in prereq.requirements(barrel):
        use = f" [{' '.join(req.use)}]" if req.use else ""
        overlay = " (GURU overlay)" if req.from_guru else ""
        note = f" — {req.note}" if req.note else ""
        env.io.out(f"{req.atom}{use}{overlay}{note}")
    if prereq.needs_guru(barrel):
        env.io.out("note: enable the GURU overlay for umu-launcher (Drydock can do this)")
    return 0


def cmd_run(args, env: DrydockEnv) -> int:
    barrel = _load(env, args.barrel)
    if barrel is None:
        return 1
    program = barrel.program(args.program)
    if program is None:
        env.io.err(f"no such program {args.program!r} in {args.barrel}")
        return 1
    return env.launch_fn(barrel, program)


# ---- barrel maintenance verbs ------------------------------------------
def cmd_winetricks(args, env: DrydockEnv) -> int:
    from gest.core.drydock import maintenance

    barrel = _load(env, args.barrel)
    if barrel is None:
        return 1
    if not args.verbs:
        env.io.err("need at least one winetricks verb (e.g. dotnet48 corefonts)")
        return 2
    rc = env.tool_spawn(maintenance.winetricks_argv(args.verbs), maintenance.barrel_env(barrel))
    if rc == 0:
        for verb in args.verbs:
            if verb not in barrel.verbs:
                barrel.verbs.append(verb)
        barrels.save_barrel(barrel, env.store_base)
        env.io.out(f"installed {' '.join(args.verbs)} into {barrel.id}")
    else:
        env.io.err(f"winetricks failed (rc={rc})")
    return rc


def cmd_winecfg(args, env: DrydockEnv) -> int:
    from gest.core.drydock import maintenance

    barrel = _load(env, args.barrel)
    if barrel is None:
        return 1
    return env.tool_spawn(maintenance.winecfg_argv(), maintenance.barrel_env(barrel))


def cmd_kill(args, env: DrydockEnv) -> int:
    from gest.core.drydock import maintenance

    barrel = _load(env, args.barrel)
    if barrel is None:
        return 1
    rc = env.tool_spawn(maintenance.kill_argv(), maintenance.barrel_env(barrel))
    env.io.out(f"killed wine processes in {barrel.id}" if rc == 0
               else f"kill failed (rc={rc})")
    return rc


def cmd_shell(args, env: DrydockEnv) -> int:
    from gest.core.drydock import maintenance

    barrel = _load(env, args.barrel)
    if barrel is None:
        return 1
    env.io.out(f"shell in {barrel.id} — WINEPREFIX={barrel.prefix or '(default)'}; exit to leave")
    return env.tool_spawn(maintenance.shell_argv(os.environ.get("SHELL", "bash")),
                          maintenance.barrel_env(barrel))


def cmd_doctor(args, env: DrydockEnv) -> int:
    from gest.core.drydock import maintenance

    missing = 0
    for tool, path, desc in maintenance.probe_tools(env.which):
        env.io.out(f"{'ok  ' if path else 'MISS'}  {tool:12}  {desc}")
        if not path:
            missing += 1
    env.io.out(f"# {missing} tool(s) missing")
    return 0


def cmd_materialize(args, env: DrydockEnv) -> int:
    from gest.core.drydock import materialize, recipe_lint, recipe_store

    try:
        recipe = recipe_store.load(args.recipe)
    except OSError as exc:
        env.io.err(f"cannot read {args.recipe}: {exc}")
        return 1
    except (RuntimeError, ValueError) as exc:
        env.io.err(str(exc))
        return 1

    if not args.no_lint:
        issues = recipe_lint.lint(recipe)
        for issue in issues:
            env.io.err(f"{issue.level}: {issue.message}")
        if recipe_lint.has_errors(issues):
            errors = sum(1 for i in issues if i.level == recipe_lint.ERROR)
            env.io.err(f"refusing to materialize — {errors} lint error(s) "
                       "(use --no-lint to override)")
            return 1

    barrel = materialize.barrel_from_recipe(recipe, args.name or "")
    if not barrel.is_valid():
        env.io.err("recipe has an invalid barrel (check runner/arch)")
        return 2
    if barrels.load_barrel(barrel.id, env.store_base) is not None and not args.force:
        env.io.err(f"barrel {barrel.id!r} already exists (use --force to overwrite)")
        return 1

    barrels.save_barrel(barrel, env.store_base)
    for program in barrel.programs:
        _write_launcher(env, barrel, program)
        _wire_customs(env, barrel, program)
    if barrel.programs:
        _refresh_db(env)
    env.io.out(f"materialized barrel {barrel.id} with {len(barrel.programs)} program(s)")
    if recipe.steps:
        env.io.out(f"note: {len(recipe.steps)} install step(s) not run — use "
                   "`drydock install-recipe` to create the barrel AND run the install")
    return 0


def cmd_install_recipe(args, env: DrydockEnv) -> int:
    """One shot: materialize the barrel, then run its install plan **against that
    barrel's own prefix** — so the install and every later launch share one
    WINEPREFIX (closes the install↔materialize seam)."""
    from pathlib import Path

    from gest.core.drydock import (
        executor,
        interpreter,
        materialize,
        recipe_lint,
        recipe_store,
    )

    try:
        recipe = recipe_store.load(args.recipe)
    except OSError as exc:
        env.io.err(f"cannot read {args.recipe}: {exc}")
        return 1
    except (RuntimeError, ValueError) as exc:
        env.io.err(str(exc))
        return 1

    if not args.no_lint:
        issues = recipe_lint.lint(recipe)
        for issue in issues:
            env.io.err(f"{issue.level}: {issue.message}")
        if recipe_lint.has_errors(issues):
            errors = sum(1 for i in issues if i.level == recipe_lint.ERROR)
            env.io.err(f"refusing to install — {errors} lint error(s) (use --no-lint to override)")
            return 1

    barrel = materialize.barrel_from_recipe(recipe, args.name or "")
    if not barrel.is_valid():
        env.io.err("recipe has an invalid barrel (check runner/arch)")
        return 2
    if barrels.load_barrel(barrel.id, env.store_base) is not None and not args.force:
        env.io.err(f"barrel {barrel.id!r} already exists (use --force to overwrite)")
        return 1

    # Save first so save_barrel pins the barrel's prefix, then plan the install
    # AGAINST that prefix — install and later launches now share one WINEPREFIX.
    barrels.save_barrel(barrel, env.store_base)
    for program in barrel.programs:
        _write_launcher(env, barrel, program)
        _wire_customs(env, barrel, program)
    if barrel.programs:
        _refresh_db(env)
    env.io.out(f"materialized barrel {barrel.id} "
               f"({len(barrel.programs)} program(s)) at {barrel.prefix}")

    ctx = interpreter.PlanContext(
        prefix=barrel.prefix,
        gamedir=str(Path(barrel.prefix) / "drive_c" / barrel.id),
        cache=args.cache or str(Path("~/.cache/drydock").expanduser() / barrel.id),
        arch=barrel.arch, runner=barrel.runner)
    ops = interpreter.plan(recipe, ctx)
    if not ops:
        env.io.out("(recipe has no install steps — barrel is ready)")
        return 0

    dry = not args.run
    runner = env.step_runner or executor.host_run
    report = executor.execute(ops, runner, dry_run=dry)
    for i, outcome in enumerate(report.outcomes, 1):
        env.io.out(f"{i:>2}. [{outcome.status}] {outcome.op.summary}")
    tail = "" if args.run else " (dry run — pass --run to execute the install on a host)"
    env.io.out(f"# install: {report.count(executor.STATUS_OK)} ok, "
               f"{report.count(executor.STATUS_FAILED)} failed, "
               f"{report.count(executor.STATUS_MANUAL)} manual, "
               f"{report.count(executor.STATUS_PLANNED)} planned, "
               f"{report.count(executor.STATUS_SKIPPED)} skipped{tail}")
    return 0 if report.ok else 1


def cmd_export_recipe(args, env: DrydockEnv) -> int:
    from gest.core.drydock import materialize, recipe_store

    barrel = _load(env, args.barrel)
    if barrel is None:
        return 1
    recipe = materialize.recipe_from_barrel(barrel)
    try:
        text = recipe_store.dumps(recipe)
    except RuntimeError as exc:  # PyYAML missing
        env.io.err(str(exc))
        return 1
    if args.output and args.output != "-":
        from pathlib import Path
        Path(args.output).expanduser().write_text(text, encoding="utf-8")
        env.io.out(f"exported barrel {barrel.id} to {args.output}")
    else:
        env.io.out(text)
    return 0


def cmd_lint(args, env: DrydockEnv) -> int:
    from gest.core.drydock import recipe_lint, recipe_store

    try:
        recipe = recipe_store.load(args.recipe)
    except OSError as exc:
        env.io.err(f"cannot read {args.recipe}: {exc}")
        return 1
    except (RuntimeError, ValueError) as exc:
        env.io.err(str(exc))
        return 1

    issues = recipe_lint.lint(recipe)
    for issue in issues:
        env.io.out(f"{issue.level}: {issue.message}")
    errors = sum(1 for i in issues if i.level == recipe_lint.ERROR)
    warnings = sum(1 for i in issues if i.level == recipe_lint.WARNING)
    if not issues:
        env.io.out("ok — no issues")
    env.io.out(f"# {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


def _plan_from_args(args):
    """Load a helm.recipe and compile it against a context derived from args.
    Returns (recipe, ops, error_message); error_message is set on failure."""
    from pathlib import Path

    from gest.core.drydock import interpreter, recipe_store

    try:
        recipe = recipe_store.load(args.recipe)
    except OSError as exc:
        return None, None, f"cannot read {args.recipe}: {exc}"
    except (RuntimeError, ValueError) as exc:
        return None, None, str(exc)

    app = barrels.slug(recipe.app_id or recipe.app_name or "app")
    base = Path("~/.local/share/hede/drydock").expanduser() / app
    prefix = args.prefix or str(base / "prefix")
    gamedir = args.gamedir or str(Path(prefix) / "drive_c" / app)
    cache = args.cache or str(Path("~/.cache/drydock").expanduser() / app)
    ctx = interpreter.PlanContext(prefix=prefix, gamedir=gamedir, cache=cache,
                                  arch=recipe.barrel.arch, runner=recipe.barrel.runner)
    return recipe, interpreter.plan(recipe, ctx), None


def cmd_plan(args, env: DrydockEnv) -> int:
    from gest.core.drydock import interpreter

    _recipe, ops, error = _plan_from_args(args)
    if error is not None:
        env.io.err(error)
        return 1
    if not ops:
        env.io.out("(recipe has no install steps)")
        return 0
    for i, op in enumerate(ops, 1):
        env.io.out(f"{i:>2}. [{op.kind}] {op.summary}")
        if op.kind == interpreter.OP_COMMAND:
            env.io.out(f"      $ {' '.join(op.argv)}")
    cmds = sum(1 for op in ops if op.kind == interpreter.OP_COMMAND)
    manual = sum(1 for op in ops if op.kind == interpreter.OP_MANUAL)
    env.io.out(f"# {len(ops)} op(s): {cmds} command(s), {manual} manual "
               "— not executed (dry run; needs host ops)")
    return 0


def cmd_install(args, env: DrydockEnv) -> int:
    from gest.core.drydock import executor, recipe_lint

    recipe, ops, error = _plan_from_args(args)
    if error is not None:
        env.io.err(error)
        return 1

    if not args.no_lint:
        issues = recipe_lint.lint(recipe)
        for issue in issues:
            env.io.err(f"{issue.level}: {issue.message}")
        if recipe_lint.has_errors(issues):
            errors = sum(1 for i in issues if i.level == recipe_lint.ERROR)
            env.io.err(f"refusing to install — {errors} lint error(s) (use --no-lint to override)")
            return 1

    if not ops:
        env.io.out("(recipe has no install steps)")
        return 0

    dry = not args.run
    runner = env.step_runner or executor.host_run
    report = executor.execute(ops, runner, dry_run=dry)
    for i, outcome in enumerate(report.outcomes, 1):
        env.io.out(f"{i:>2}. [{outcome.status}] {outcome.op.summary}")
    tail = "" if args.run else " (dry run — pass --run to execute on a host)"
    env.io.out(f"# {report.count(executor.STATUS_OK)} ok, "
               f"{report.count(executor.STATUS_FAILED)} failed, "
               f"{report.count(executor.STATUS_MANUAL)} manual, "
               f"{report.count(executor.STATUS_PLANNED)} planned, "
               f"{report.count(executor.STATUS_SKIPPED)} skipped{tail}")
    return 0 if report.ok else 1


COMMANDS: dict[str, Callable[..., int]] = {
    "create": cmd_create, "list": cmd_list, "show": cmd_show, "rm": cmd_rm,
    "register": cmd_register, "scan": cmd_scan, "prereqs": cmd_prereqs, "run": cmd_run,
    "materialize": cmd_materialize, "plan": cmd_plan, "install": cmd_install,
    "install-recipe": cmd_install_recipe,
    "lint": cmd_lint, "export-recipe": cmd_export_recipe,
    "winetricks": cmd_winetricks, "winecfg": cmd_winecfg, "kill": cmd_kill,
    "shell": cmd_shell, "doctor": cmd_doctor,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="drydock",
                                     description="Manage Wine/Proton barrels and Windows apps.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create a barrel")
    create.add_argument("name")
    create.add_argument("--runner", required=True, choices=RUNNERS)
    create.add_argument("--version", default="", help="Proton codename/path or wine target")
    create.add_argument("--arch", choices=ARCHES, default="win64")
    create.add_argument("--dxvk", action="store_true")
    create.add_argument("--vkd3d", action="store_true")

    sub.add_parser("list", help="list barrels")

    reg = sub.add_parser("register", help="add a program + a launcher")
    reg.add_argument("barrel")
    reg.add_argument("exe")
    reg.add_argument("--name", required=True)
    reg.add_argument("--game", action="store_true")
    for flag in ("gamescope", "fsr", "hdr", "gamemode", "mangohud"):
        reg.add_argument(f"--{flag}", action="store_true")

    scan = sub.add_parser("scan", help="adopt wine's auto-generated launchers")
    scan.add_argument("barrel")
    scan.add_argument("--wine-apps-dir", default="")

    for name in ("show", "rm", "prereqs"):
        sub.add_parser(name, help=f"{name} a barrel").add_argument("barrel")

    run = sub.add_parser("run", help="launch a program")
    run.add_argument("barrel")
    run.add_argument("program")

    mat = sub.add_parser("materialize", help="create a barrel from a helm.recipe")
    mat.add_argument("recipe", help="path to a helm.recipe YAML file")
    mat.add_argument("--name", default="", help="override the barrel id/name")
    mat.add_argument("--force", action="store_true", help="overwrite an existing barrel")
    mat.add_argument("--no-lint", action="store_true",
                     help="skip the recipe lint check (materialize even with errors)")

    pl = sub.add_parser("plan", help="show the install plan compiled from a helm.recipe")
    inst = sub.add_parser("install", help="run a helm.recipe's install plan (dry run unless --run)")
    for parser_ in (pl, inst):
        parser_.add_argument("recipe", help="path to a helm.recipe YAML file")
        parser_.add_argument("--prefix", default="", help="WINEPREFIX ($WINEPREFIX)")
        parser_.add_argument("--gamedir", default="", help="install root ($GAMEDIR)")
        parser_.add_argument("--cache", default="", help="download cache ($CACHE)")
    inst.add_argument("--run", action="store_true",
                      help="execute the plan for real on this host (needs wine, etc.)")
    inst.add_argument("--no-lint", action="store_true",
                      help="skip the recipe lint check (install even with errors)")

    insr = sub.add_parser("install-recipe",
                          help="one shot: create the barrel from a recipe AND run its install")
    insr.add_argument("recipe", help="path to a helm.recipe YAML file")
    insr.add_argument("--name", default="", help="override the barrel id/name")
    insr.add_argument("--force", action="store_true", help="overwrite an existing barrel")
    insr.add_argument("--run", action="store_true",
                      help="execute the install for real on this host (needs wine, etc.)")
    insr.add_argument("--no-lint", action="store_true", help="skip the recipe lint check")
    insr.add_argument("--cache", default="", help="download cache ($CACHE)")

    lint = sub.add_parser("lint", help="validate a helm.recipe (structure + references)")
    lint.add_argument("recipe", help="path to a helm.recipe YAML file")

    exp = sub.add_parser("export-recipe", help="export a barrel's config as a helm.recipe")
    exp.add_argument("barrel")
    exp.add_argument("-o", "--output", default="-", help="write the recipe here (default: stdout)")

    wt = sub.add_parser("winetricks", help="run winetricks verbs in a barrel")
    wt.add_argument("barrel")
    wt.add_argument("verbs", nargs="*", help="e.g. dotnet48 corefonts vcrun2019")
    for name in ("winecfg", "kill", "shell"):
        sub.add_parser(name, help=f"{name} in a barrel's prefix").add_argument("barrel")
    sub.add_parser("doctor", help="report which host tools are installed")
    return parser


def run_cli(argv=None, *, env: DrydockEnv | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = env or DrydockEnv()
    return COMMANDS[args.command](args, env)


def main() -> None:
    sys.exit(run_cli())


def open_main() -> None:
    """Entry point for ``drydock-run <barrel> <program>``."""
    sys.exit(run_cli(["run", *sys.argv[1:]]))


if __name__ == "__main__":
    main()
