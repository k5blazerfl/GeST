"""``flotilla`` — manage VMs (vessels) over libvirt/QEMU.

Pure, TTY-free command layer: each ``cmd_*`` takes parsed args + an injectable
:class:`FlotillaEnv` and returns an exit code. The libvirt host operations
(virsh/virt-viewer/qemu-img) run through ``env.run_argv``, so the whole command
layer is CI-testable without libvirt.

    flotilla create win11 --os windows --memory 8192 --iso Win11.iso
    flotilla xml win11            # the compiled libvirt domain XML
    flotilla define win11         # register it with libvirtd
    flotilla start win11
    flotilla console win11        # SPICE/VNC console (the traditional way)
    flotilla prereqs win11
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from gest.core.flotilla import backend, domainxml, model, prereq, vessels
from gest.core.flotilla.model import DISPLAYS, OSES, Disk, Vessel


@dataclass
class CliIO:
    out: Callable[[str], None]
    err: Callable[[str], None]


def _default_io() -> CliIO:
    return CliIO(out=print, err=lambda s: print(s, file=sys.stderr))


def _default_run(argv: list[str]) -> int:
    try:
        return subprocess.run(argv).returncode
    except FileNotFoundError:
        return 127


@dataclass
class FlotillaEnv:
    io: CliIO = field(default_factory=_default_io)
    store_base: str = vessels.FLOTILLA_DIR
    uri: str = backend.URI_SESSION
    # Runs a libvirt host tool (virsh/virt-viewer/qemu-img); injectable for tests.
    run_argv: Callable[[list[str]], int] = _default_run


def _load(env: FlotillaEnv, vessel_id: str) -> Vessel | None:
    vessel = vessels.load_vessel(vessel_id, env.store_base)
    if vessel is None:
        env.io.err(f"no such vessel {vessel_id!r}")
    return vessel


def cmd_create(args, env: FlotillaEnv) -> int:
    vid = vessels.slug(args.name)
    vessel = model.recommended(args.os, args.name, vid)
    if args.memory:
        vessel.memory_mb = args.memory
    if args.vcpus:
        vessel.vcpus = args.vcpus
    if args.display:
        vessel.display = args.display
    vessel.install_iso = args.iso or ""
    vessel.virtio_iso = args.virtio_iso or ""
    disk = Disk(path=str(vessels.default_disk_path(vid, env.store_base)), size_gb=args.disk_size)
    vessel.disks = [disk]

    if not vessel.is_valid():
        env.io.err("invalid vessel (check --os / --display)")
        return 2
    if vessels.load_vessel(vid, env.store_base) is not None:
        env.io.err(f"vessel {vid!r} already exists")
        return 1

    vessels.save_vessel(vessel, env.store_base)
    env.io.out(f"created vessel {vid} ({vessel.os}, {vessel.vcpus} vCPU, "
               f"{vessel.memory_mb} MiB, {vessel.firmware})")
    if args.allocate:
        rc = env.run_argv(backend.alloc_disk_argv(disk.path, disk.size_gb, disk.fmt))
        env.io.out(f"allocated a {disk.size_gb}G disk at {disk.path}" if rc == 0
                   else f"disk allocation failed (rc={rc})")
    else:
        env.io.out(f"note: allocate the disk with --allocate (or "
                   f"`qemu-img create -f qcow2 {disk.path} {disk.size_gb}G`)")
    return 0


def cmd_list(args, env: FlotillaEnv) -> int:
    for vid in vessels.list_vessels(env.store_base):
        env.io.out(vid)
    return 0


def cmd_show(args, env: FlotillaEnv) -> int:
    vessel = _load(env, args.id)
    if vessel is None:
        return 1
    env.io.out(f"{vessel.name} [{vessel.id}]  os={vessel.os}  firmware={vessel.firmware}"
               + ("  +secureboot" if vessel.secureboot else "")
               + ("  +tpm2" if vessel.tpm else ""))
    env.io.out(f"  {vessel.vcpus} vCPU, {vessel.memory_mb} MiB, display={vessel.display}, "
               f"entry={vessel.entry}")
    for disk in vessel.disks:
        env.io.out(f"  disk: {disk.path} ({disk.size_gb}G {disk.fmt})")
    if vessel.install_iso:
        env.io.out(f"  install: {vessel.install_iso}")
    return 0


def cmd_xml(args, env: FlotillaEnv) -> int:
    vessel = _load(env, args.id)
    if vessel is None:
        return 1
    env.io.out(domainxml.compile_domain(vessel))
    return 0


def cmd_prereqs(args, env: FlotillaEnv) -> int:
    vessel = _load(env, args.id)
    if vessel is None:
        return 1
    for req in prereq.requirements(vessel):
        use = f" [{' '.join(req.use)}]" if req.use else ""
        src = "" if req.from_portage else "  (not in Portage — fetched)"
        note = f" — {req.note}" if req.note else ""
        env.io.out(f"{req.atom}{use}{src}{note}")
    env.io.out(f"service: enable+start {', '.join(prereq.SERVICES)}; "
               f"groups: add your user to {', '.join(prereq.GROUPS)}")
    return 0


def cmd_define(args, env: FlotillaEnv) -> int:
    vessel = _load(env, args.id)
    if vessel is None:
        return 1
    path = vessels.write_domain_xml(vessel.id, domainxml.compile_domain(vessel), env.store_base)
    rc = env.run_argv(backend.define_argv(env.uri, str(path)))
    env.io.out(f"defined {vessel.id} from {path}" if rc == 0
               else f"virsh define failed (rc={rc})")
    return rc


def cmd_start(args, env: FlotillaEnv) -> int:
    if _load(env, args.id) is None:
        return 1
    rc = env.run_argv(backend.start_argv(env.uri, args.id))
    env.io.out(f"started {args.id}" if rc == 0 else f"start failed (rc={rc})")
    return rc


def cmd_stop(args, env: FlotillaEnv) -> int:
    if _load(env, args.id) is None:
        return 1
    argv = (backend.destroy_argv if args.force else backend.shutdown_argv)(env.uri, args.id)
    rc = env.run_argv(argv)
    verb = "forced off" if args.force else "shutting down"
    env.io.out(f"{verb} {args.id}" if rc == 0 else f"stop failed (rc={rc})")
    return rc


def cmd_console(args, env: FlotillaEnv) -> int:
    if _load(env, args.id) is None:
        return 1
    return env.run_argv(backend.console_argv(env.uri, args.id))


def cmd_rm(args, env: FlotillaEnv) -> int:
    if vessels.load_vessel(args.id, env.store_base) is None:
        env.io.err(f"no such vessel {args.id!r}")
        return 1
    env.run_argv(backend.undefine_argv(env.uri, args.id))  # best-effort (may be undefined)
    if vessels.delete_vessel(args.id, env.store_base):
        env.io.out(f"removed vessel {args.id}")
        return 0
    return 1


COMMANDS: dict[str, Callable[..., int]] = {
    "create": cmd_create, "list": cmd_list, "show": cmd_show, "xml": cmd_xml,
    "prereqs": cmd_prereqs, "define": cmd_define, "start": cmd_start, "stop": cmd_stop,
    "console": cmd_console, "rm": cmd_rm,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flotilla", description="Manage VMs (vessels).")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create a vessel")
    create.add_argument("name")
    create.add_argument("--os", choices=OSES, default="linux")
    create.add_argument("--memory", type=int, default=0, help="MiB (0 = OS default)")
    create.add_argument("--vcpus", type=int, default=0, help="0 = default")
    create.add_argument("--disk-size", type=int, default=40, help="GiB")
    create.add_argument("--iso", default="", help="install ISO")
    create.add_argument("--virtio-iso", default="", help="virtio-win ISO (Windows)")
    create.add_argument("--display", choices=DISPLAYS, default="")
    create.add_argument("--allocate", action="store_true", help="qemu-img create the disk now")

    sub.add_parser("list", help="list vessels")
    for name in ("show", "xml", "prereqs", "define", "start", "console"):
        sub.add_parser(name, help=f"{name} a vessel").add_argument("id")

    stop = sub.add_parser("stop", help="shut down a vessel")
    stop.add_argument("id")
    stop.add_argument("--force", action="store_true", help="force off (destroy)")

    sub.add_parser("rm", help="undefine + delete a vessel").add_argument("id")
    return parser


def run_cli(argv=None, *, env: FlotillaEnv | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = env or FlotillaEnv()
    return COMMANDS[args.command](args, env)


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
