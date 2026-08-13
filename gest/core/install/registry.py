"""The install step registry — the twenty Handbook steps wired to real modules.

Each row of docs/design/installer-flow-engine.md §3 becomes one
:class:`~gest.core.install.step.InstallStep` here, calling an *existing* module
function (nothing is reimplemented). :func:`build_registry` returns the ordered
list the engine runs; the ordering is the tested contract.

Two rows in the design table are structural, not executing steps:

* row 2 ``MakeFilesystems`` is *folded into* the Partition step — ``provision``'s
  own ``plan_steps`` runs mkfs/mkswap/swapon as part of ``apply_plan``. It is kept
  as a registry row (so the table maps 1:1) whose work is already done once
  Partition has run, so it is always ``is_satisfied`` behind the partition marker.
* row 20 teardown is the engine's ``finally`` (``teardown_chroot``), never a step,
  so it is not emitted here.

Config writes (rows 5-6, 11-13, 18) render with the core function and write on the
host via :func:`write_under_root` — the target is not running, so there is no live
command and no D-Bus. Chroot rows (8-10, 14-17) are ``ArgvStep``s: the engine hands
them ``ctx.target`` (a ``ChrootExecutor``) so their argv gets the ``chroot <root>``
prefix for free.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
from collections.abc import Callable

from gest.core import rootpath
from gest.core.bootloader.install import install_steps
from gest.core.chroot.prepare import prepare_chroot
from gest.core.disk import mount as disk_mount
from gest.core.disk import provision
from gest.core.eselect.commands import set_argv
from gest.core.exec.runner import OnProgress
from gest.core.exec.steps import Step
from gest.core.install.context import InstallContext
from gest.core.install.plan import InstallPlan, Phase
from gest.core.install.step import ArgvStep, FuncStep, InstallStep
from gest.core.install.write import write_under_root
from gest.core.kernel.build import build_steps
from gest.core.network import hosts as net_hosts
from gest.core.network import netifrc
from gest.core.network import resolv as net_resolv
from gest.core.portage import paths
from gest.core.portage.codec import shell
from gest.core.stage3 import commands as stage3_commands
from gest.core.stage3 import index as stage3_index
from gest.core.stage3 import verify as stage3_verify
from gest.core.system import console as sys_console
from gest.core.system import hostname as sys_hostname
from gest.core.system import locale as sys_locale
from gest.core.system import timezone as sys_timezone
from gest.core.users.commands import chpasswd_input, gpasswd_argv, useradd_argv

_ZONEINFO = "/usr/share/zoneinfo"


def _emit(on_progress: OnProgress | None, *lines: str) -> None:
    if on_progress is not None and lines:
        on_progress(list(lines))


# --- phase 1: prepare disk --------------------------------------------------

class Partition(FuncStep):
    """Provision the disk (partition + mkfs/swap, folded) via ``apply_plan``."""

    label = "Partition the disk"
    phase = Phase.PREPARE_DISK
    key = "partition"

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        await provision.apply_plan(
            ctx.plan.disk, ctx.host, ctx.devices, ctx.mounts,
            boot_source=None, on_progress=on_progress)

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        # Destructive: only skipped behind an explicit completion marker (§6).
        return ctx.state.done(self.key)


class MakeFilesystems(FuncStep):
    """Folded into :class:`Partition` (``provision.plan_steps`` runs the mkfs)."""

    label = "Make filesystems"
    phase = Phase.PREPARE_DISK

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        # No work of its own: apply_plan already ran mkfs/mkswap/swapon.
        _emit(on_progress, "filesystems created during partitioning")

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return ctx.state.done("partition")


class MountTarget(FuncStep):
    """Mount the target filesystems under ``ctx.root`` (``apply_mount_plan``)."""

    label = "Mount the target"
    phase = Phase.PREPARE_DISK
    target_aware = True

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        await disk_mount.apply_mount_plan(ctx.plan.mount, ctx.host, on_progress=on_progress)

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return os.path.ismount(ctx.root)


# --- phase 2: base system ---------------------------------------------------

class UnpackStage3(FuncStep):
    """Download, verify (mandatory) and unpack the stage3 into ``ctx.root``.

    Uses the pure stage3 core (``index``/``verify``/``commands``) over the host
    executor — the same download → hash-gate → best-effort-gpg → tar sequence the
    backend runs, but on the direct/live-CD path. The integrity check is
    mandatory: a hash mismatch raises **before** ``tar`` is ever invoked.
    """

    label = "Unpack the stage3 tarball"
    phase = Phase.BASE_SYSTEM
    target_aware = True
    key = "unpack_stage3"

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        sel = ctx.plan.stage3
        disk_mount.guard_target_root(ctx.root)          # rejects "/"
        digests_text = stage3_index.fetch_text(sel.digests_url)
        # Stage the large tarball on the target's own filesystem (ample space).
        workdir = tempfile.mkdtemp(dir=ctx.root, prefix=".gest-stage3-")
        try:
            tarball = os.path.join(workdir, sel.filename)
            _emit(on_progress, f"Downloading {sel.filename}", f"  from {sel.url}")
            res = await ctx.host.run(
                stage3_commands.download_argv(sel.url, tarball), on_progress=on_progress)
            if res.code != 0:
                raise ValueError(f"stage3 download failed (exit {res.code})")

            sig = tarball + ".asc"
            sig_ok = False
            if sel.signature_url.startswith(("https://", "http://")):
                sres = await ctx.host.run(
                    stage3_commands.download_argv(sel.signature_url, sig),
                    on_progress=on_progress)
                sig_ok = sres.code == 0 and os.path.exists(sig)

            _emit(on_progress, "Verifying integrity (BLAKE2B + SHA512)…")
            with open(tarball, "rb") as fh:
                data = fh.read()
            expected = stage3_verify.parse_digests(digests_text, sel.filename)
            if not stage3_verify.verify_hashes(data, expected):
                raise ValueError(
                    "stage3 integrity check failed (missing or mismatched "
                    "BLAKE2B/SHA512) — refusing to unpack")
            _emit(on_progress, f"  integrity OK ({', '.join(sorted(expected))})")

            if sig_ok:
                _emit(on_progress, "Verifying GPG signature (best-effort)…")
                await ctx.host.run(
                    stage3_commands.gpg_verify_argv(sig, tarball), on_progress=on_progress)

            _emit(on_progress, f"Unpacking into {ctx.root}…")
            unres = await ctx.host.run(
                stage3_commands.tar_unpack_argv(tarball, ctx.root), on_progress=on_progress)
            if unres.code != 0:
                raise ValueError(f"stage3 unpack failed (exit {unres.code})")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        release = os.path.exists(rootpath.resolve(ctx.root, "/etc/gentoo-release"))
        return release and ctx.state.done(self.key)


class WriteFstab(FuncStep):
    """Generate + write the target's ``/etc/fstab`` from the plan and UUIDs."""

    label = "Generate /etc/fstab"
    phase = Phase.BASE_SYSTEM
    target_aware = True

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        text = disk_mount.generate_target_fstab(ctx.plan.mount, ctx.uuids)
        path = disk_mount.write_target_fstab_file(ctx.root, text)
        _emit(on_progress, f"wrote {path}")

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return os.path.exists(rootpath.resolve(ctx.root, "/etc/fstab"))


class WriteMakeConf(FuncStep):
    """Upsert ``MAKEOPTS`` into the target's ``make.conf`` (stage3 ships one)."""

    label = "Write make.conf"
    phase = Phase.BASE_SYSTEM
    target_aware = True

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        conf = paths.make_conf(ctx.root)
        try:
            with open(conf, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            text = ""
        jobs = ctx.plan.kernel.jobs if ctx.plan.kernel.jobs > 0 else 1
        rendered = shell.render(text, "MAKEOPTS", f"-j{jobs}")
        path = write_under_root(ctx.root, "/etc/portage/make.conf", rendered)
        _emit(on_progress, f"wrote {path}")

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return os.path.exists(rootpath.resolve(ctx.root, "/etc/portage/make.conf"))


class PrepareChroot(FuncStep):
    """Mount the pseudo-filesystems and copy DNS into ``ctx.root``."""

    label = "Prepare the chroot"
    phase = Phase.BASE_SYSTEM
    target_aware = True
    opens_chroot = True

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        await prepare_chroot(ctx.root, ctx.host, on_progress=on_progress)

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return os.path.ismount(rootpath.resolve(ctx.root, "/proc"))


class SyncTree(ArgvStep):
    """``emerge --sync`` inside the target."""

    label = "Sync the Portage tree"
    phase = Phase.BASE_SYSTEM
    chroot = True
    key = "sync_tree"

    def build(self, ctx: InstallContext) -> list[Step]:
        return [Step("sync portage tree", ["emerge", "--sync", "--color", "n"])]

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return ctx.state.done(self.key)


class SetProfile(ArgvStep):
    """``eselect profile set <n>`` inside the target (before @world, §12 q2)."""

    label = "Select the profile"
    phase = Phase.BASE_SYSTEM
    chroot = True

    def build(self, ctx: InstallContext) -> list[Step]:
        return [Step(f"set profile {ctx.plan.profile}",
                     set_argv("profile", ctx.plan.profile))]
    # No cheap host-side probe: the profile number maps to a path only via the
    # target's own eselect list. Setting a profile is idempotent, so re-run.


class EmergeWorld(ArgvStep):
    """``emerge -uDN [--getbinpkg] @world`` inside the target."""

    label = "Emerge @world"
    phase = Phase.BASE_SYSTEM
    chroot = True
    key = "emerge_world"

    def build(self, ctx: InstallContext) -> list[Step]:
        argv = ["emerge", "-uDN", "--color", "n"]
        if ctx.plan.binary_pref:                 # BINPREF: prefer binpkg, else source
            argv.insert(1, "--getbinpkg")
        return [Step("emerge @world", [*argv, "@world"])]

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return ctx.state.done(self.key)


# --- phase 3: configure -----------------------------------------------------

class SetTimezoneLocale(FuncStep):
    """Write ``/etc/timezone`` (+ localtime symlink) and the locale files."""

    label = "Set timezone and locale"
    phase = Phase.CONFIGURE
    target_aware = True

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        zone = ctx.plan.timezone
        if not sys_timezone.valid_zone_name(zone):
            raise ValueError(f"invalid timezone: {zone!r}")
        write_under_root(ctx.root, "/etc/timezone", f"{zone}\n")
        # Point <root>/etc/localtime at the absolute zoneinfo path (valid inside
        # the target too, so there is no live command to skip).
        target = f"{_ZONEINFO}/{zone}"
        localtime = rootpath.resolve(ctx.root, "/etc/localtime")
        tmp = rootpath.resolve(ctx.root, "/etc/.gest.localtime")
        os.makedirs(os.path.dirname(localtime), exist_ok=True)
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        os.symlink(target, tmp)
        os.replace(tmp, localtime)

        lang = ctx.plan.locale
        if not sys_locale.valid_locale(lang):
            raise ValueError(f"invalid locale: {lang!r}")
        write_under_root(ctx.root, "/etc/env.d/02locale", f'LANG="{lang}"\n')
        write_under_root(ctx.root, "/etc/locale.conf", f"LANG={lang}\n")
        _emit(on_progress, f"timezone {zone}, locale {lang}")

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        tzp = rootpath.resolve(ctx.root, "/etc/timezone")
        lcp = rootpath.resolve(ctx.root, "/etc/locale.conf")
        try:
            with open(tzp, encoding="utf-8") as fh:
                zone_ok = fh.read().strip() == ctx.plan.timezone
        except OSError:
            return False
        return zone_ok and os.path.exists(lcp)


class SetHostname(FuncStep):
    """Write the OpenRC ``/etc/conf.d/hostname``."""

    label = "Set the hostname"
    phase = Phase.CONFIGURE
    target_aware = True

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        name = ctx.plan.hostname
        if not sys_hostname.valid_hostname(name):
            raise ValueError(f"invalid hostname: {name!r}")
        path = write_under_root(ctx.root, "/etc/conf.d/hostname", f'hostname="{name}"\n')
        _emit(on_progress, f"wrote {path}")

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        path = rootpath.resolve(ctx.root, "/etc/conf.d/hostname")
        try:
            with open(path, encoding="utf-8") as fh:
                return sys_hostname.parse_conf_hostname(fh.read()) == ctx.plan.hostname
        except OSError:
            return False


class SetConsole(FuncStep):
    """Upsert the console keymap into ``/etc/conf.d/keymaps`` (preserving the file)."""

    label = "Set the console keymap"
    phase = Phase.CONFIGURE
    target_aware = True

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        keymap = ctx.plan.keymap
        if not sys_console.valid_keymap(keymap):
            raise ValueError(f"invalid keymap: {keymap!r}")
        path = rootpath.resolve(ctx.root, sys_console.KEYMAPS_CONF)
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            text = ""
        rendered = sys_console.set_conf_value(text, "keymap", keymap)
        written = write_under_root(ctx.root, sys_console.KEYMAPS_CONF, rendered)
        _emit(on_progress, f"wrote {written}")

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        path = rootpath.resolve(ctx.root, sys_console.KEYMAPS_CONF)
        try:
            with open(path, encoding="utf-8") as fh:
                return sys_console.parse_conf_value(fh.read(), "keymap") == ctx.plan.keymap
        except OSError:
            return False


# --- phase 4: kernel & boot -------------------------------------------------

class BuildKernel(ArgvStep):
    """Build the kernel inside the target (``kernel.build_steps``)."""

    label = "Build the kernel"
    phase = Phase.KERNEL_BOOT
    chroot = True
    key = "build_kernel"

    def build(self, ctx: InstallContext) -> list[Step]:
        return build_steps(ctx.plan.kernel)

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return ctx.state.done(self.key)


class InstallBootloader(ArgvStep):
    """Install GRUB + regenerate its config inside the target (``install_steps``)."""

    label = "Install the bootloader"
    phase = Phase.KERNEL_BOOT
    chroot = True
    target_aware = True          # uses the boot_directory/efi_directory seam (§3¹)
    key = "install_bootloader"

    def build(self, ctx: InstallContext) -> list[Step]:
        return install_steps(ctx.plan.bootloader)

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return ctx.state.done(self.key)


# --- phase 5: users & network -----------------------------------------------

class SetRootPassword(ArgvStep):
    """Set the root password via ``chpasswd`` inside the target.

    The password is NOT in the plan. It is supplied at run time via
    :attr:`secret` (a callable the reviewed flow sets before running), validated
    and turned into ``(argv, stdin)`` by ``users.chpasswd_input`` so it never
    lands in argv or a log. See :attr:`stdin`.
    """

    label = "Set the root password"
    phase = Phase.USERS_NETWORK
    chroot = True

    #: Callable[[], str] returning the password; set by the caller before run.
    secret = None

    def __init__(self) -> None:
        self.stdin = ""          # the "root:<pw>\n" chpasswd feeds on stdin

    def build(self, ctx: InstallContext) -> list[Step]:
        if self.secret is None:
            raise ValueError("no root-password secret supplied to SetRootPassword")
        argv, self.stdin = chpasswd_input("root", self.secret())
        # The password rides on the Step's stdin (the executor pipes it to
        # chpasswd), so it is never in argv, a log, or the process list.
        return [Step("set root password", argv, stdin=self.stdin)]

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        # Idempotent and cheap to re-apply; only skipped when not requested.
        return not ctx.plan.root_password


class CreateUser(ArgvStep):
    """Create the optional non-root user and add it to ``wheel``."""

    label = "Create the user account"
    phase = Phase.USERS_NETWORK
    chroot = True

    def build(self, ctx: InstallContext) -> list[Step]:
        user = ctx.plan.user
        if user is None:
            return []
        steps = [Step(f"create user {user.name}",
                      useradd_argv(user.name, comment=user.comment, shell=user.shell))]
        if user.wheel:
            steps.append(Step(f"add {user.name} to wheel",
                              gpasswd_argv("wheel", user.name, add=True)))
        return steps

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        user = ctx.plan.user
        if user is None:
            return True
        path = rootpath.resolve(ctx.root, "/etc/passwd")
        try:
            with open(path, encoding="utf-8") as fh:
                return any(line.split(":", 1)[0] == user.name for line in fh)
        except OSError:
            return False


class ConfigureNetwork(FuncStep):
    """Write netifrc ``/etc/conf.d/net``, ``/etc/resolv.conf`` and ``/etc/hosts``."""

    label = "Configure the network"
    phase = Phase.USERS_NETWORK
    target_aware = True

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        net = ctx.plan.network
        if net.interface:
            method = "dhcp" if net.dhcp else "static"
            cfg = netifrc.InterfaceConfig(
                net.interface, method=method, address=net.address, gateway=net.gateway)
            if method == "static":
                if not netifrc.valid_address(net.address):
                    raise ValueError(f"invalid interface address: {net.address!r}")
                if not netifrc.valid_gateway(net.gateway):
                    raise ValueError(f"invalid gateway: {net.gateway!r}")
            path = rootpath.resolve(ctx.root, "/etc/conf.d/net")
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                text = ""
            write_under_root(ctx.root, "/etc/conf.d/net", netifrc.render_conf_net(text, cfg))

        if net.nameservers:
            servers = list(net.nameservers)
            if not net_resolv.valid_resolv(servers, []):
                raise ValueError("invalid nameservers")
            write_under_root(ctx.root, "/etc/resolv.conf",
                             net_resolv.render_resolv(servers, []))

        write_under_root(ctx.root, "/etc/hosts",
                         net_hosts.render_hosts(net_hosts.default_hosts()))
        _emit(on_progress, "network configuration written")

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return os.path.exists(rootpath.resolve(ctx.root, "/etc/hosts"))


# --- phase 6: finish (tier-2 opt-in) ----------------------------------------

def _tier2_steps(plan: InstallPlan) -> list[InstallStep]:
    """Expand ``plan.tier2`` (row 19) into extra steps — empty by default.

    Day-2 modules (sshd/firewall/privilege/sysctl) are opt-in and off by default
    (§12 q4); wiring them is a separable follow-on, so a request for one is
    refused loudly rather than silently skipped.
    """
    if not plan.tier2:
        return []
    raise ValueError(
        "tier-2 install modules are not wired in step 4b: "
        f"{', '.join(sorted(plan.tier2))}")


Secret = Callable[[], str]


def _root_password_step(root_secret: Secret | None) -> SetRootPassword:
    """A ``SetRootPassword`` with its run-time secret callable wired in (if given)."""
    step = SetRootPassword()
    if root_secret is not None:
        step.secret = root_secret
    return step


def build_registry(plan: InstallPlan, *, root_secret: Secret | None = None) -> list[InstallStep]:
    """The full ordered install steps for ``plan``, in Handbook order (the contract).

    Row 2 (``MakeFilesystems``) is folded into ``Partition`` and row 20 (teardown)
    is the engine's ``finally``; row 19 (tier-2) expands via :func:`_tier2_steps`
    (empty by default). ``root_secret`` (a ``Callable[[], str]``) is supplied at run
    time and wired into ``SetRootPassword`` — never stored in the plan. The order of
    this list is what a test pins.
    """
    steps: list[InstallStep] = [
        Partition(),
        MakeFilesystems(),
        MountTarget(),
        UnpackStage3(),
        WriteFstab(),
        WriteMakeConf(),
        PrepareChroot(),
        SyncTree(),
        SetProfile(),
        EmergeWorld(),
        SetTimezoneLocale(),
        SetHostname(),
        SetConsole(),
        BuildKernel(),
        InstallBootloader(),
        _root_password_step(root_secret),
        CreateUser(),
        ConfigureNetwork(),
    ]
    steps.extend(_tier2_steps(plan))
    return steps


def build_minimal_registry(
    plan: InstallPlan, *, root_secret: Secret | None = None
) -> list[InstallStep]:
    """The smallest ordered set of steps that produces a *bootable* system (§9c).

    A strict subset of :func:`build_registry`: the boot-critical path only —
    partition → mount → stage3 → fstab → make.conf → prepare-chroot → sync →
    profile → @world → kernel → bootloader → root password. It drops the
    day-1-nicety config steps (timezone/locale, hostname, console keymap) and the
    optional user, network and tier-2 steps; those layer back in via
    :func:`build_registry`. The installed system boots to a root login; the rest
    is configured on first boot or a fuller run.
    """
    return [
        Partition(),
        MakeFilesystems(),
        MountTarget(),
        UnpackStage3(),
        WriteFstab(),
        WriteMakeConf(),
        PrepareChroot(),
        SyncTree(),
        SetProfile(),
        EmergeWorld(),
        BuildKernel(),
        InstallBootloader(),
        _root_password_step(root_secret),
    ]
