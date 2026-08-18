"""``drydock`` — manage Wine/Proton bottles and launch Windows apps.

Pure, TTY-free command layer: each ``cmd_*`` takes parsed args + an injectable
:class:`DrydockEnv` and returns an exit code. ``drydock-run <bottle> <program>``
is the stub the synthesized ``.desktop`` Exec points at.

    drydock create office --runner wine --arch win32
    drydock register office /prefix/excel.exe --name Excel --gamescope --fsr
    drydock scan office            # adopt wine's auto-generated launchers
    drydock prereqs office
    drydock run office excel
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from gest.core.customs.desktop import remove_entry, write_entry
from gest.core.drydock import bottles, desktop, launch, prereq
from gest.core.drydock.model import ARCHES, RUNNERS, Bottle, GraphicsProfile, Program


@dataclass
class CliIO:
    out: Callable[[str], None]
    err: Callable[[str], None]


def _default_io() -> CliIO:
    return CliIO(out=print, err=lambda s: print(s, file=sys.stderr))


@dataclass
class DrydockEnv:
    io: CliIO = field(default_factory=_default_io)
    store_base: str = bottles.DRYDOCK_DIR
    applications_dir: str = "~/.local/share/applications"
    wine_apps_dir: str = desktop.WINE_APPS_DIR
    launch_fn: Callable = launch.launch


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
            remove_entry(desktop.desktop_id(bottle.id, program.id), env.applications_dir)
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
    env.io.out(f"registered {program.id}; launcher {_write_launcher(env, bottle, program)}")
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
        env.io.out(f"adopted {program.name} ({program.exe})")
        count += 1
    bottles.save_bottle(bottle, env.store_base)
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


def cmd_import_lutris(args, env: DrydockEnv) -> int:
    from gest.core.drydock import lutris_import

    try:
        with open(os.path.expanduser(args.script), encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        env.io.err(f"cannot read {args.script}: {exc}")
        return 1
    try:
        script = lutris_import.load_script(text)
    except (RuntimeError, ValueError) as exc:
        env.io.err(str(exc))
        return 1

    result = lutris_import.convert(script)
    if result.recipe is None:
        for reason in result.rejected:
            env.io.err(f"rejected: {reason}")
        env.io.err("import failed — nothing to write")
        return 1
    for warning in result.warnings:
        env.io.err(f"warning: {warning}")
    for reason in result.rejected:
        env.io.err(f"dropped: {reason}")

    try:
        out = lutris_import.dump_recipe(result.recipe)
    except RuntimeError as exc:
        env.io.err(str(exc))
        return 1
    if args.output and args.output != "-":
        with open(os.path.expanduser(args.output), "w", encoding="utf-8") as fh:
            fh.write(out)
        env.io.out(f"wrote recipe to {args.output}")
    else:
        env.io.out(out)
    env.io.out(f"# {len(result.recipe.steps)} step(s), {result.manual_steps} manual "
               f"TODO(s), {len(result.warnings)} warning(s), {len(result.rejected)} dropped")
    return 0


COMMANDS: dict[str, Callable[..., int]] = {
    "create": cmd_create, "list": cmd_list, "show": cmd_show, "rm": cmd_rm,
    "register": cmd_register, "scan": cmd_scan, "prereqs": cmd_prereqs, "run": cmd_run,
    "import-lutris": cmd_import_lutris,
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

    imp = sub.add_parser("import-lutris",
                         help="convert a Lutris install script to a helm.recipe")
    imp.add_argument("script", help="path to a Lutris .yml install script")
    imp.add_argument("-o", "--output", default="-",
                     help="write the recipe here (default: stdout)")
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
