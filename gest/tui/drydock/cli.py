"""``drydock`` — manage Wine/Proton bottles and launch Windows apps.

Pure, TTY-free command layer: each ``cmd_*`` takes parsed args + an injectable
:class:`DrydockEnv` and returns an exit code. ``drydock-run <bottle> <program>``
is the stub the synthesized ``.desktop`` Exec points at.

    drydock create office --runner wine --arch win32
    drydock register office /prefix/excel.exe --name Excel --gamescope --fsr
    drydock scan office            # adopt wine's auto-generated launchers
    drydock materialize game.recipe   # create a bottle from a helm.recipe
    drydock plan game.recipe          # show the compiled install plan (dry run)
    drydock install game.recipe --run # execute the install plan on this host
    drydock prereqs office
    drydock run office excel
"""

from __future__ import annotations

import argparse
import contextlib
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from gest.core.customs import icons, identity_store, mime
from gest.core.customs.desktop import remove_entry, write_entry
from gest.core.drydock import bottles, desktop, launch, prereq
from gest.core.drydock.model import ARCHES, RUNNERS, Bottle, GraphicsProfile, Program


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


@dataclass
class DrydockEnv:
    io: CliIO = field(default_factory=_default_io)
    store_base: str = bottles.DRYDOCK_DIR
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


def _load(env: DrydockEnv, bottle_id: str) -> Bottle | None:
    bottle = bottles.load_bottle(bottle_id, env.store_base)
    if bottle is None:
        env.io.err(f"no such bottle {bottle_id!r}")
    return bottle


def _write_launcher(env: DrydockEnv, bottle: Bottle, program: Program) -> str:
    path = write_entry(desktop.desktop_entry(bottle, program),
                       desktop.desktop_id(bottle.id, program.id), env.applications_dir)
    return str(path)


def _upsert_program(bottle: Bottle, program: Program) -> None:
    bottle.programs = [p for p in bottle.programs if p.id != program.id]
    bottle.programs.append(program)


def _identity_path(env: DrydockEnv) -> str | None:
    return env.identity_path or None


def _wire_customs(env: DrydockEnv, bottle: Bottle, program: Program) -> None:
    """Make a synthesized launcher a first-class HeDE citizen: extract its icon,
    register its taskbar identity, and set it as the default handler for its MIME
    types. The DB refresh is left to :func:`_refresh_db` so a batch (scan) does it
    once. Host tools run through ``env.run_argv``; failures are non-fatal."""
    did = desktop.desktop_id(bottle.id, program.id)

    # 1. Icon: wrestool extracts the .exe's group-icon → icotool renders a PNG
    #    into the hicolor theme under the launcher's Icon name (<desktop_id>).
    exe = desktop.local_exe_path(bottle, program)
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
    bottle = Bottle(id=bottles.slug(args.name), name=args.name, runner=args.runner,
                    runner_version=args.version, arch=args.arch,
                    dxvk=args.dxvk, vkd3d=args.vkd3d)
    if not bottle.is_valid():
        env.io.err("invalid bottle (check --runner and --arch)")
        return 2
    path = bottles.save_bottle(bottle, env.store_base)
    env.io.out(f"created bottle {bottle.id} ({path})")
    return 0


def cmd_list(args, env: DrydockEnv) -> int:
    for bid in bottles.list_bottles(env.store_base):
        env.io.out(bid)
    return 0


def cmd_show(args, env: DrydockEnv) -> int:
    bottle = _load(env, args.bottle)
    if bottle is None:
        return 1
    runner = f"{bottle.runner}" + (f" {bottle.runner_version}" if bottle.runner_version else "")
    env.io.out(f"{bottle.name} [{bottle.id}]  runner={runner}  arch={bottle.arch}")
    env.io.out(f"prefix: {bottle.prefix}")
    for program in bottle.programs:
        env.io.out(f"  - {program.id}: {program.name}  ({program.exe})")
    return 0


def cmd_rm(args, env: DrydockEnv) -> int:
    bottle = bottles.load_bottle(args.bottle, env.store_base)
    if bottle is not None:
        for program in bottle.programs:
            did = desktop.desktop_id(bottle.id, program.id)
            remove_entry(did, env.applications_dir)
            identity_store.unregister_entry(did, _identity_path(env))
            with contextlib.suppress(OSError):
                icons.icon_install_path(did, theme_dir=env.icon_theme_dir).unlink()
        if bottle.programs:
            _refresh_db(env)
    if bottles.delete_bottle(args.bottle, env.store_base):
        env.io.out(f"removed bottle {args.bottle}")
        return 0
    env.io.err(f"no such bottle {args.bottle!r}")
    return 1


def _graphics_from_args(args) -> GraphicsProfile:
    return GraphicsProfile(gamescope=args.gamescope, fsr=args.fsr, hdr=args.hdr,
                           gamemode=args.gamemode, mangohud=args.mangohud)


def cmd_register(args, env: DrydockEnv) -> int:
    bottle = _load(env, args.bottle)
    if bottle is None:
        return 1
    program = Program(id=bottles.slug(args.name), name=args.name, exe=args.exe,
                      category="Game" if args.game else "Application",
                      graphics=_graphics_from_args(args))
    _upsert_program(bottle, program)
    bottles.save_bottle(bottle, env.store_base)
    launcher = _write_launcher(env, bottle, program)
    _wire_customs(env, bottle, program)
    _refresh_db(env)
    env.io.out(f"registered {program.id}; launcher {launcher} (icon + identity + MIME wired)")
    return 0


def cmd_scan(args, env: DrydockEnv) -> int:
    bottle = _load(env, args.bottle)
    if bottle is None:
        return 1
    wine_dir = args.wine_apps_dir or env.wine_apps_dir
    count = 0
    for entry in desktop.harvest_dir(wine_dir):
        program = desktop.program_from_harvested(entry, bottles.slug(entry.name or "app"))
        _upsert_program(bottle, program)
        _write_launcher(env, bottle, program)
        _wire_customs(env, bottle, program)
        env.io.out(f"adopted {program.name} ({program.exe})")
        count += 1
    bottles.save_bottle(bottle, env.store_base)
    if count:
        _refresh_db(env)
    env.io.out(f"{count} app(s) adopted")
    return 0


def cmd_prereqs(args, env: DrydockEnv) -> int:
    bottle = _load(env, args.bottle)
    if bottle is None:
        return 1
    for req in prereq.requirements(bottle):
        use = f" [{' '.join(req.use)}]" if req.use else ""
        overlay = " (GURU overlay)" if req.from_guru else ""
        note = f" — {req.note}" if req.note else ""
        env.io.out(f"{req.atom}{use}{overlay}{note}")
    if prereq.needs_guru(bottle):
        env.io.out("note: enable the GURU overlay for umu-launcher (Drydock can do this)")
    return 0


def cmd_run(args, env: DrydockEnv) -> int:
    bottle = _load(env, args.bottle)
    if bottle is None:
        return 1
    program = bottle.program(args.program)
    if program is None:
        env.io.err(f"no such program {args.program!r} in {args.bottle}")
        return 1
    return env.launch_fn(bottle, program)


def cmd_materialize(args, env: DrydockEnv) -> int:
    from gest.core.drydock import materialize, recipe_store

    try:
        recipe = recipe_store.load(args.recipe)
    except OSError as exc:
        env.io.err(f"cannot read {args.recipe}: {exc}")
        return 1
    except (RuntimeError, ValueError) as exc:
        env.io.err(str(exc))
        return 1

    bottle = materialize.bottle_from_recipe(recipe, args.name or "")
    if not bottle.is_valid():
        env.io.err("recipe has an invalid bottle (check runner/arch)")
        return 2
    if bottles.load_bottle(bottle.id, env.store_base) is not None and not args.force:
        env.io.err(f"bottle {bottle.id!r} already exists (use --force to overwrite)")
        return 1

    bottles.save_bottle(bottle, env.store_base)
    for program in bottle.programs:
        _write_launcher(env, bottle, program)
        _wire_customs(env, bottle, program)
    if bottle.programs:
        _refresh_db(env)
    env.io.out(f"materialized bottle {bottle.id} with {len(bottle.programs)} program(s)")
    if recipe.steps:
        env.io.out(f"note: {len(recipe.steps)} install step(s) not run "
                   "(needs host ops — roadmap phase 4/6)")
    return 0


def _plan_from_args(args):
    """Load a helm.recipe and compile it against a context derived from args.
    Returns (ops, error_message); error_message is set on failure."""
    from pathlib import Path

    from gest.core.drydock import interpreter, recipe_store

    try:
        recipe = recipe_store.load(args.recipe)
    except OSError as exc:
        return None, f"cannot read {args.recipe}: {exc}"
    except (RuntimeError, ValueError) as exc:
        return None, str(exc)

    app = bottles.slug(recipe.app_id or recipe.app_name or "app")
    base = Path("~/.local/share/hede/drydock").expanduser() / app
    prefix = args.prefix or str(base / "prefix")
    gamedir = args.gamedir or str(Path(prefix) / "drive_c" / app)
    cache = args.cache or str(Path("~/.cache/drydock").expanduser() / app)
    ctx = interpreter.PlanContext(prefix=prefix, gamedir=gamedir, cache=cache,
                                  arch=recipe.bottle.arch, runner=recipe.bottle.runner)
    return interpreter.plan(recipe, ctx), None


def cmd_plan(args, env: DrydockEnv) -> int:
    from gest.core.drydock import interpreter

    ops, error = _plan_from_args(args)
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
    from gest.core.drydock import executor

    ops, error = _plan_from_args(args)
    if error is not None:
        env.io.err(error)
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
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="drydock",
                                     description="Manage Wine/Proton bottles and Windows apps.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create a bottle")
    create.add_argument("name")
    create.add_argument("--runner", required=True, choices=RUNNERS)
    create.add_argument("--version", default="", help="Proton codename/path or wine target")
    create.add_argument("--arch", choices=ARCHES, default="win64")
    create.add_argument("--dxvk", action="store_true")
    create.add_argument("--vkd3d", action="store_true")

    sub.add_parser("list", help="list bottles")

    reg = sub.add_parser("register", help="add a program + a launcher")
    reg.add_argument("bottle")
    reg.add_argument("exe")
    reg.add_argument("--name", required=True)
    reg.add_argument("--game", action="store_true")
    for flag in ("gamescope", "fsr", "hdr", "gamemode", "mangohud"):
        reg.add_argument(f"--{flag}", action="store_true")

    scan = sub.add_parser("scan", help="adopt wine's auto-generated launchers")
    scan.add_argument("bottle")
    scan.add_argument("--wine-apps-dir", default="")

    for name in ("show", "rm", "prereqs"):
        sub.add_parser(name, help=f"{name} a bottle").add_argument("bottle")

    run = sub.add_parser("run", help="launch a program")
    run.add_argument("bottle")
    run.add_argument("program")

    mat = sub.add_parser("materialize", help="create a bottle from a helm.recipe")
    mat.add_argument("recipe", help="path to a helm.recipe YAML file")
    mat.add_argument("--name", default="", help="override the bottle id/name")
    mat.add_argument("--force", action="store_true", help="overwrite an existing bottle")

    pl = sub.add_parser("plan", help="show the install plan compiled from a helm.recipe")
    inst = sub.add_parser("install", help="run a helm.recipe's install plan (dry run unless --run)")
    for parser_ in (pl, inst):
        parser_.add_argument("recipe", help="path to a helm.recipe YAML file")
        parser_.add_argument("--prefix", default="", help="WINEPREFIX ($WINEPREFIX)")
        parser_.add_argument("--gamedir", default="", help="install root ($GAMEDIR)")
        parser_.add_argument("--cache", default="", help="download cache ($CACHE)")
    inst.add_argument("--run", action="store_true",
                      help="execute the plan for real on this host (needs wine, etc.)")
    return parser


def run_cli(argv=None, *, env: DrydockEnv | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = env or DrydockEnv()
    return COMMANDS[args.command](args, env)


def main() -> None:
    sys.exit(run_cli())


def open_main() -> None:
    """Entry point for ``drydock-run <bottle> <program>``."""
    sys.exit(run_cli(["run", *sys.argv[1:]]))


if __name__ == "__main__":
    main()
