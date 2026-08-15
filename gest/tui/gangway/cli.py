"""``gangway`` — manage and launch RDP profiles from the terminal.

The command layer is pure and TTY-free: each ``cmd_*`` takes parsed args and an
injectable :class:`GangwayEnv` (IO + the store dir + the launch/credential-store
callables) and returns an exit code. ``gangway-open <name>`` is the stub the
synthesized ``.desktop`` entry's ``Exec`` points at.

    gangway add work --host pc.corp --user bob --domain CORP
    gangway set-password work
    gangway install work        # add a launcher to helm-menu
    gangway open work           # launch (fetches the password from the keychain)
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from gest.core.customs.desktop import remove_entry, write_entry
from gest.core.rdp import creds, launcher, run, store
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


@dataclass
class GangwayEnv:
    io: CliIO = field(default_factory=_default_io)
    store_base: str = store.GANGWAY_DIR
    applications_dir: str = "~/.local/share/applications"
    launch_fn: Callable = run.launch
    cred_store: Callable = creds.store


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


def cmd_open(args, env: GangwayEnv) -> int:
    profile = store.load_profile(args.name, env.store_base)
    if profile is None:
        env.io.err(f"no such profile {args.name!r}")
        return 1
    share = os.path.expanduser("~") if profile.drive_redirect else None
    return env.launch_fn(profile, share_path=share)


COMMANDS: dict[str, Callable[..., int]] = {
    "list": cmd_list, "add": cmd_add, "rm": cmd_rm, "show": cmd_show,
    "set-password": cmd_set_password, "install": cmd_install, "open": cmd_open,
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

    for name in ("rm", "show", "set-password", "install", "open"):
        sub.add_parser(name, help=f"{name} a profile").add_argument("name")
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


if __name__ == "__main__":
    main()
