"""``gangway`` — manage and launch RDP profiles from the terminal.

The command layer is pure and TTY-free: each ``cmd_*`` takes parsed args and an
injectable :class:`GangwayEnv` (IO + the store dir + the launch/credential-store
callables) and returns an exit code. ``gangway-open <name>`` is the stub the
synthesized ``.desktop`` entry's ``Exec`` points at.

    gangway add work --host pc.corp --user bob --domain CORP
    gangway set-password work
    gangway install work        # add a launcher to helm-menu
    gangway open work           # launch (fetches the password from the keychain)
    gangway open work --dry-run # print the FreeRDP command instead of launching
    gangway register-handler    # make Gangway the default .rdp / rdp:// handler
    gangway open-file some.rdp  # launch a .rdp file ad-hoc (no saved profile)
    gangway import some.rdp     # save a .rdp file as a named profile
    gangway export work -o work.rdp   # share a saved profile as a .rdp
    gangway discover 192.168.1.0/24 --add   # find RDP hosts on the LAN, save them
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from gest.core.customs import identity_store, mime
from gest.core.customs.desktop import remove_entry, write_entry
from gest.core.rdp import creds, discover, launcher, rdpfile, run, store
from gest.core.rdp import target as rdptarget
from gest.core.rdp.model import QUALITIES, RdpProfile


@dataclass
class CliIO:
    out: Callable[[str], None]
    err: Callable[[str], None]
    ask_password: Callable[[str], str]


def _default_io() -> CliIO:
    import getpass

    return CliIO(out=print, err=lambda s: print(s, file=sys.stderr),
                 ask_password=getpass.getpass)


def _default_run(argv: list[str]) -> int:
    try:
        return subprocess.run(argv).returncode
    except FileNotFoundError:
        return 127


@dataclass
class GangwayEnv:
    io: CliIO = field(default_factory=_default_io)
    store_base: str = store.GANGWAY_DIR
    applications_dir: str = "~/.local/share/applications"
    launch_fn: Callable = run.launch
    cred_store: Callable = creds.store
    # Host tool runner (xdg-mime / update-desktop-database) — injectable for tests.
    run_argv: Callable[[list[str]], int] = _default_run
    identity_path: str = ""  # shared Customs identity map; empty → default path
    port_probe: discover.Probe = discover.probe_port  # injectable for tests


def _profile_from_args(args) -> RdpProfile:
    return RdpProfile(
        name=args.name, host=args.host, port=args.port,
        username=args.user, domain=args.domain,
        fullscreen=not args.windowed, width=args.width, height=args.height,
        multimon=args.multimon, gateway_host=args.gateway, quality=args.quality,
        clipboard=not args.no_clipboard, drive_redirect=not args.no_drive,
        audio_output=not args.no_audio, microphone=args.mic, printers=args.printers,
        nla=not args.no_nla,
    )


def cmd_list(args, env: GangwayEnv) -> int:
    for name in store.list_profiles(env.store_base):
        env.io.out(name)
    return 0


def cmd_add(args, env: GangwayEnv) -> int:
    profile = _profile_from_args(args)
    if not profile.is_valid():
        env.io.err("invalid profile (need a host, a valid port and quality)")
        return 2
    path = store.save_profile(profile, env.store_base)
    env.io.out(f"saved {path}")
    return 0


def cmd_rm(args, env: GangwayEnv) -> int:
    if store.delete_profile(args.name, env.store_base):
        remove_entry(launcher.desktop_id(args.name), env.applications_dir)
        env.io.out(f"removed {args.name}")
        return 0
    env.io.err(f"no such profile {args.name!r}")
    return 1


def cmd_show(args, env: GangwayEnv) -> int:
    profile = store.load_profile(args.name, env.store_base)
    if profile is None:
        env.io.err(f"no such profile {args.name!r}")
        return 1
    env.io.out(f"host: {profile.host}:{profile.port}")
    env.io.out(f"user: {profile.username or '(prompt)'}")
    if profile.domain:
        env.io.out(f"domain: {profile.domain}")
    env.io.out(f"quality: {profile.quality}")
    env.io.out(f"redirect: clipboard={profile.clipboard} drive={profile.drive_redirect} "
               f"audio={profile.audio_output} mic={profile.microphone}")
    return 0


def cmd_set_password(args, env: GangwayEnv) -> int:
    profile = store.load_profile(args.name, env.store_base)
    if profile is None:
        env.io.err(f"no such profile {args.name!r}")
        return 1
    password = env.io.ask_password(f"Password for {profile.username or profile.host}: ")
    if env.cred_store(profile.credential_attributes(), f"Gangway: {profile.name}", password):
        env.io.out("password stored in the keychain")
        return 0
    env.io.err("could not store the password (is a Secret Service running?)")
    return 1


def cmd_install(args, env: GangwayEnv) -> int:
    profile = store.load_profile(args.name, env.store_base)
    if profile is None:
        env.io.err(f"no such profile {args.name!r}")
        return 1
    path = write_entry(launcher.desktop_entry(profile),
                       launcher.desktop_id(profile.name), env.applications_dir)
    env.io.out(f"installed launcher {path}")
    return 0


def _launch(env: GangwayEnv, profile: RdpProfile, *, dry_run: bool) -> int:
    """Launch a profile, or (dry run) print the FreeRDP command that would run.
    Dry run fetches no password, so ``/from-stdin`` is omitted."""
    share = os.path.expanduser("~") if profile.drive_redirect else None
    if dry_run:
        from gest.core.rdp import commands
        env.io.out(" ".join(commands.build_argv(profile, share_path=share, from_stdin=False)))
        return 0
    return env.launch_fn(profile, share_path=share)


def cmd_open(args, env: GangwayEnv) -> int:
    profile = store.load_profile(args.name, env.store_base)
    if profile is None:
        env.io.err(f"no such profile {args.name!r}")
        return 1
    if args.windowed:
        profile.fullscreen = False
    elif args.fullscreen:
        profile.fullscreen = True
    return _launch(env, profile, dry_run=args.dry_run)


def cmd_open_file(args, env: GangwayEnv) -> int:
    try:
        profile = rdptarget.profile_from_target(args.target)
    except OSError as exc:
        env.io.err(f"cannot open {args.target}: {exc}")
        return 1
    if not profile.is_valid():
        env.io.err(f"{args.target}: not a usable RDP target (need a host)")
        return 1
    return _launch(env, profile, dry_run=args.dry_run)


def cmd_import(args, env: GangwayEnv) -> int:
    try:
        profile = rdptarget.profile_from_file(args.file)
    except OSError as exc:
        env.io.err(f"cannot read {args.file}: {exc}")
        return 1
    if args.name:
        profile.name = args.name
    if not profile.is_valid():
        env.io.err(f"{args.file}: not a usable RDP profile (need a host)")
        return 1
    path = store.save_profile(profile, env.store_base)
    env.io.out(f"imported {profile.name} ({path})")
    return 0


def cmd_export(args, env: GangwayEnv) -> int:
    profile = store.load_profile(args.name, env.store_base)
    if profile is None:
        env.io.err(f"no such profile {args.name!r}")
        return 1
    text = rdpfile.render(profile)
    if args.output and args.output != "-":
        Path(args.output).expanduser().write_text(text, encoding="utf-8")
        env.io.out(f"exported {args.name} to {args.output}")
    else:
        env.io.out(text)
    return 0


def cmd_discover(args, env: GangwayEnv) -> int:
    try:
        total = discover.host_count(args.cidr)  # cheap — no enumeration yet
    except ValueError as exc:
        env.io.err(f"invalid CIDR {args.cidr!r}: {exc}")
        return 2
    if total > args.max:
        env.io.err(f"{args.cidr} covers {total} hosts (> --max {args.max}); "
                   "narrow the range or raise --max")
        return 2

    found = discover.scan(args.cidr, port=args.port, probe=env.port_probe, timeout=args.timeout)
    for host in found:
        env.io.out(f"{host.host}:{host.port}")
    if args.add:
        for host in found:
            store.save_profile(discover.profile_from_discovered(host), env.store_base)
        env.io.out(f"added {len(found)} profile(s)")
    env.io.out(f"# {len(found)} host(s) with port {args.port} open "
               f"(scanned {total})")
    return 0


def cmd_register_handler(args, env: GangwayEnv) -> int:
    path = write_entry(launcher.handler_desktop_entry(),
                       launcher.HANDLER_DESKTOP_ID, env.applications_dir)
    env.run_argv(mime.register_default_argv(launcher.HANDLER_DESKTOP_ID, mime.GANGWAY_TYPES))
    env.run_argv(mime.update_database_argv(env.applications_dir))
    # Give every FreeRDP window the handler's identity in the taskbar (shared
    # across profiles — full-desktop RDP can't be told apart until RAIL).
    identity_store.register_entry(launcher.FREERDP_WM_CLASSES, launcher.HANDLER_DESKTOP_ID,
                                  env.identity_path or None)
    env.io.out(f"registered .rdp / rdp:// handler + taskbar identity ({path})")
    return 0


def cmd_unregister_handler(args, env: GangwayEnv) -> int:
    removed = remove_entry(launcher.HANDLER_DESKTOP_ID, env.applications_dir)
    identity_store.unregister_entry(launcher.HANDLER_DESKTOP_ID, env.identity_path or None)
    env.run_argv(mime.update_database_argv(env.applications_dir))
    env.io.out("removed the .rdp / rdp:// handler" if removed else "no handler was installed")
    return 0


COMMANDS: dict[str, Callable[..., int]] = {
    "list": cmd_list, "add": cmd_add, "rm": cmd_rm, "show": cmd_show,
    "set-password": cmd_set_password, "install": cmd_install, "open": cmd_open,
    "open-file": cmd_open_file, "register-handler": cmd_register_handler,
    "unregister-handler": cmd_unregister_handler,
    "import": cmd_import, "export": cmd_export, "discover": cmd_discover,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gangway", description="Manage/launch RDP profiles.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list profiles")

    add = sub.add_parser("add", help="create/replace a profile")
    add.add_argument("name")
    add.add_argument("--host", required=True)
    add.add_argument("--port", type=int, default=3389)
    add.add_argument("--user", default="")
    add.add_argument("--domain", default="")
    add.add_argument("--gateway", default="")
    add.add_argument("--quality", choices=QUALITIES, default="balanced")
    add.add_argument("--windowed", action="store_true")
    add.add_argument("--width", type=int, default=1920)
    add.add_argument("--height", type=int, default=1080)
    add.add_argument("--multimon", action="store_true")
    add.add_argument("--no-clipboard", action="store_true")
    add.add_argument("--no-drive", action="store_true")
    add.add_argument("--no-audio", action="store_true")
    add.add_argument("--mic", action="store_true")
    add.add_argument("--printers", action="store_true")
    add.add_argument("--no-nla", action="store_true")

    for name in ("rm", "show", "set-password", "install"):
        sub.add_parser(name, help=f"{name} a profile").add_argument("name")

    opn = sub.add_parser("open", help="launch a saved profile")
    opn.add_argument("name")
    opn.add_argument("--dry-run", action="store_true",
                     help="print the FreeRDP command instead of launching")
    screen = opn.add_mutually_exclusive_group()
    screen.add_argument("--windowed", action="store_true",
                        help="override: connect in a window")
    screen.add_argument("--fullscreen", action="store_true",
                        help="override: connect fullscreen")

    of = sub.add_parser("open-file", help="launch a .rdp file or rdp:// URI ad-hoc")
    of.add_argument("target", help="a .rdp file path, a file:// URL, or an rdp:// URI")
    of.add_argument("--dry-run", action="store_true",
                    help="print the FreeRDP command instead of launching")
    sub.add_parser("register-handler", help="make Gangway the default .rdp/rdp:// handler")
    sub.add_parser("unregister-handler", help="remove the .rdp/rdp:// handler")

    imp = sub.add_parser("import", help="import a .rdp file as a saved profile")
    imp.add_argument("file", help="path to a .rdp file")
    imp.add_argument("--name", default="", help="profile name (default: the file stem)")

    exp = sub.add_parser("export", help="export a saved profile to a .rdp file")
    exp.add_argument("name")
    exp.add_argument("-o", "--output", default="-", help="write the .rdp here (default: stdout)")

    disc = sub.add_parser("discover", help="scan a subnet for hosts with the RDP port open")
    disc.add_argument("cidr", help="a network range, e.g. 192.168.1.0/24 (or a single IP)")
    disc.add_argument("--port", type=int, default=discover.RDP_PORT)
    disc.add_argument("--timeout", type=float, default=0.3, help="per-host probe timeout (s)")
    disc.add_argument("--max", type=int, default=1024, help="refuse ranges larger than this")
    disc.add_argument("--add", action="store_true", help="save each found host as a profile")
    return parser


def run_cli(argv=None, *, env: GangwayEnv | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = env or GangwayEnv()
    return COMMANDS[args.command](args, env)


def main() -> None:
    sys.exit(run_cli())


def open_main() -> None:
    """Entry point for ``gangway-open <name>`` (the .desktop Exec stub)."""
    sys.exit(run_cli(["open", *sys.argv[1:]]))


def open_file_main() -> None:
    """Entry point for ``gangway-rdp-open <target>`` — the MIME/URI handler stub
    (its ``.desktop`` Exec passes a ``.rdp`` file or ``rdp://`` URI as ``%u``)."""
    sys.exit(run_cli(["open-file", *sys.argv[1:]]))


if __name__ == "__main__":
    main()
