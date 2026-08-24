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

import asyncio
import contextlib
import os
import shutil
import tempfile
from collections.abc import Callable

from gest.core import rootpath
from gest.core.bootloader import m1n1
from gest.core.bootloader.install import install_steps
from gest.core.chroot.prepare import prepare_chroot
from gest.core.disk import fstab as disk_fstab
from gest.core.disk import mount as disk_mount
from gest.core.disk import provision
from gest.core.disk import reader as disk_reader
from gest.core.eselect.commands import set_argv
from gest.core.exec.runner import OnProgress, RunResult
from gest.core.exec.steps import Step, StepError, run_steps
from gest.core.firewall import nft as fw_nft
from gest.core.firewall.model import FirewallPolicy
from gest.core.hwflags import detect as hwdetect
from gest.core.install import desktop, gpu
from gest.core.install.context import InstallContext
from gest.core.install.plan import (
    InstallPlan,
    Phase,
    installs_escalator,
    license_accept_value,
)
from gest.core.install.step import ArgvStep, FuncStep, InstallStep
from gest.core.install.write import write_under_root
from gest.core.kernel import config as kconfig
from gest.core.kernel.build import build_steps
from gest.core.network import hosts as net_hosts
from gest.core.network import netifrc
from gest.core.network import resolv as net_resolv
from gest.core.portage import paths
from gest.core.portage.codec import shell
from gest.core.privilege import render as priv_render
from gest.core.privilege.model import DOAS_CONF, SUDOERS_DROPIN, EscalationPolicy
from gest.core.sshd import config as sshd_config
from gest.core.sshd.model import SshdSettings
from gest.core.sshd.reader import SSHD_CONFIG
from gest.core.stage3 import commands as stage3_commands
from gest.core.stage3 import index as stage3_index
from gest.core.stage3 import verify as stage3_verify
from gest.core.sysctl import config as sysctl_config
from gest.core.sysctl.config import SYSCTL_DROPIN
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
        # Quiet util-linux mount's repeating "your fstab has been modified — run
        # systemctl daemon-reload" advisory: reload systemd's fstab view ONCE up
        # front so the per-device target mounts below don't each print the hint.
        # Best-effort — on a host without systemd this is a harmless no-op.
        with contextlib.suppress(Exception):
            await ctx.host.run(["systemctl", "daemon-reload"])
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
        # UUIDs come from ctx.uuids when the caller pre-populated them (tests do);
        # otherwise read them live from the filesystems the Partition step just
        # made — the real install path, where nothing filled ctx.uuids in advance.
        uuids = ctx.uuids or {
            dev: disk_reader.device_uuid(dev)
            for dev in disk_mount.fstab_devices(ctx.plan.mount)
        }
        text = disk_mount.generate_target_fstab(ctx.plan.mount, uuids)
        path = disk_mount.write_target_fstab_file(ctx.root, text)
        _emit(on_progress, f"wrote {path}")

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        # The stage3 ALWAYS ships a template /etc/fstab (every entry commented out),
        # so a bare os.path.exists() wrongly marks this done and SKIPS it — leaving
        # the template with no root entry. systemd-remount-fs then never remounts /
        # read-write, so /etc/machine-id can't be written and systemd-logind's state
        # dir can't be created → no seat → a black desktop. Only satisfied once a
        # *valid generated* fstab (at least one real entry) is on disk.
        path = rootpath.resolve(ctx.root, "/etc/fstab")
        if not os.path.exists(path):
            return False
        with open(path) as fh:
            return disk_fstab.valid_generated_fstab(fh.read())


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
        # ACCEPT_LICENSE policy — set before @world so licensed atoms (firmware,
        # NVIDIA-r2, EULA packages) resolve per the reviewed rung.
        rendered = shell.render(rendered, "ACCEPT_LICENSE",
                                license_accept_value(ctx.plan.license))
        # VIDEO_CARDS must be set before @world so mesa/xorg build with the right
        # driver USE; the driver packages themselves come later (InstallGpuDrivers).
        cards = gpu.video_cards_value(ctx.plan.gpu)
        if cards:
            rendered = shell.render(rendered, "VIDEO_CARDS", cards)
        # CPU_FLAGS_X86 — always hardware-probed (no decision); best-effort, so a
        # host without cpuid2cpuflags just leaves the stage3 default in place.
        cpu_flags = hwdetect.detect_cpu_flags()
        if cpu_flags:
            rendered = shell.render(rendered, "CPU_FLAGS_X86", " ".join(cpu_flags))
        # System-wide USE from the wizard's Features checklist (explicit +/- both ways).
        if ctx.plan.global_use:
            rendered = shell.render(rendered, "USE", " ".join(ctx.plan.global_use))
        # Source builds only: tune for this CPU. Binpkgs use the binhost's flags, so
        # COMMON_FLAGS/RUSTFLAGS only bite when compiling — it's a consequence of the
        # build-strategy fork, not a separate decision.
        if not ctx.plan.binary_pref:
            rendered = shell.render(rendered, "COMMON_FLAGS", "-march=native -O2 -pipe")
            rendered = shell.render(rendered, "RUSTFLAGS", "-C target-cpu=native")
        # Custom-role raw overrides, overlaid last (last-wins over everything above).
        for name, value in ctx.plan.make_conf_overrides:
            rendered = shell.render(rendered, name, value)
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
    """``emerge --sync`` inside the target, with retry + a webrsync fallback.

    A plain ``emerge --sync`` fails hard on a *transient* mirror inconsistency —
    most often a gemato Manifest/tree mismatch while a public rsync mirror is
    mid-update — which would otherwise abort the whole install for something that
    clears itself in a minute. So we retry a few times with a short backoff, and
    if it still won't take, fall back to ``emerge-webrsync``: that pulls a signed
    daily snapshot tarball over HTTP instead of rsync, sidestepping the mirror's
    momentary state entirely.
    """

    label = "Sync the Portage tree"
    phase = Phase.BASE_SYSTEM
    chroot = True
    key = "sync_tree"

    _SYNC = ["emerge", "--sync", "--color", "n"]
    _WEBRSYNC = ["emerge-webrsync"]
    _RETRIES = 3        # emerge --sync attempts before the webrsync fallback
    _BACKOFF = 5.0      # seconds between --sync attempts (0 in tests)

    def build(self, ctx: InstallContext) -> list[Step]:
        # The primary path (kept for the registry contract + as the argv of record).
        return [Step("sync portage tree", self._SYNC)]

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        executor = ctx.executor_for(self.chroot)
        last: RunResult | None = None
        for attempt in range(1, self._RETRIES + 1):
            if attempt > 1:
                if on_progress is not None:
                    on_progress([f"emerge --sync failed; retry {attempt}/{self._RETRIES}…"])
                if self._BACKOFF:
                    await asyncio.sleep(self._BACKOFF)   # let the mirror settle
            last = await executor.run(self._SYNC, on_progress=on_progress)
            if last.code == 0:
                return
        # rsync path exhausted — fall back to the HTTP snapshot tarball.
        if on_progress is not None:
            on_progress(["emerge --sync still failing; falling back to emerge-webrsync…"])
        res = await executor.run(self._WEBRSYNC, on_progress=on_progress)
        if res.code == 0:
            return
        # Both paths failed; surface the last --sync failure for context.
        raise StepError(Step("sync portage tree", self._SYNC), last or res)

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


class ProvisionDesktop(FuncStep):
    """Make the HeDE desktop installable in the target, offline (``plan.desktop``).

    The GeSI live image *is* a HeDE system, so this runs host-side (no chroot):
    ``quickpkg @installed`` repackages every installed package straight into the
    target's pkgdir (so ``InstallDesktop``'s ``--usepkgonly`` never compiles), then
    seeds the Amphitheater overlay + a git-backed ``repos.conf`` for day-2 updates.
    See ``desktop.py`` / ``docs/design/desktop-provisioning.md``. No-op for base
    Gentoo.
    """

    label = "Provision the Helm Desktop Environment"
    phase = Phase.BASE_SYSTEM
    target_aware = True          # writes into the target root from the live host
    key = "provision_desktop"

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        if not ctx.plan.desktop:
            return
        root = ctx.root
        steps = [
            Step("repackage the live system into binpkgs",
                 desktop.quickpkg_argv(pkgdir=f"{root}{desktop.PKGDIR}")),
            # Always make /var/db/repos so the overlay can be seeded OR git-synced
            # into it (the CLI path clones the overlay here at install time).
            Step("prepare the overlay dir", desktop.overlay_parent_argv(root=root)),
        ]
        # Seed the overlay CONTENT only if the live env actually ships it — the
        # barebones CLI ISO has none, and fetches it over the network instead (see
        # InstallDesktop). The git-backed repos.conf below both enables that fetch
        # and lets the installed system `emerge --sync` it later.
        if os.path.isdir(desktop.OVERLAY_LOCATION):
            steps.append(
                Step("seed the Amphitheater overlay", desktop.seed_overlay_argv(root=root)))
        else:
            _emit(on_progress, f"{desktop.OVERLAY_LOCATION} not present — the overlay "
                  "will be git-synced into the target at desktop-install time")
        await run_steps(steps, ctx.host, on_progress=on_progress)
        write_under_root(
            root, "/etc/portage/repos.conf/amphitheater.conf", desktop.repos_conf())
        # Accept the ~arch keyword for gest/hede so --usepkgonly can install them.
        kw = write_under_root(
            root, desktop.ACCEPT_KEYWORDS, desktop.accept_keywords(ctx.plan.arch))
        # …and the USE the closure needs (qtbase[wayland,widgets] is a hard hede
        # DEPEND; gest[qt] for the Control Center) — mirrors the build's package.use.
        pu = write_under_root(root, desktop.PACKAGE_USE, desktop.package_use())
        _emit(on_progress, f"wrote repos.conf + {kw} + {pu}")
        # Replace quickpkg's broken binpkgs for image-mutating packages (e.g.
        # xkeyboard-config — see desktop.BINPKG_FIXUP_DIR) with the real,
        # source-built binpkgs the ISO ships. No-op if the image ships no fixups.
        target_pkgdir = f"{root}{desktop.PKGDIR}"
        fixups = desktop.binpkg_fixup_pairs(target_pkgdir=target_pkgdir)
        for src, dst in fixups:
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copytree(src, dst)
        if fixups:
            _emit(on_progress, f"swapped {len(fixups)} quickpkg binpkg(s) for shipped "
                  "real binpkgs (image-mutating preinst)")
        ctx.state.mark(self)

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return not ctx.plan.desktop or ctx.state.done(self.key)


class InstallDesktop(ArgvStep):
    """Emerge the HeDE desktop into the target (``plan.desktop``); recorded in @world.

    A no-op for a base-Gentoo install (``desktop=False``). Runs after
    ``ProvisionDesktop`` (which planted the binpkgs + overlay) and before the
    kernel/boot phase, so plymouth + the HeDE theme are present when a seamless
    build bakes the splash (``genkernel --plymouth``) and stages the GRUB theme.
    ``--usepkgonly`` installs from the quickpkg'd binpkgs — offline, no recompile.
    """

    label = "Install the Helm Desktop Environment"
    phase = Phase.BASE_SYSTEM
    chroot = True
    key = "install_desktop"

    def build(self, ctx: InstallContext) -> list[Step]:
        if not ctx.plan.desktop:
            return []
        if desktop.has_desktop_binpkg(ctx.root):
            # Desktop ISO: the quickpkg'd binpkgs are complete → binary-only, offline.
            return [
                # Rebuild PKGDIR/Packages so the index matches the fixup binpkgs
                # ProvisionDesktop swapped in (else --usepkgonly rejects them).
                Step("refresh the binpkg index", desktop.regen_binhost_argv()),
                Step("emerge the HeDE desktop", desktop.emerge_desktop_argv()),
            ]
        # CLI ISO: no local HeDE binpkgs. Reach gui-apps/hede via the overlay, then
        # emerge from the binhost (falling back to building from the tree). If the ISO
        # didn't seed the overlay content, git-sync it first — which needs dev-vcs/git,
        # absent from the base stage3.
        steps: list[Step] = []
        if not desktop.overlay_seeded(ctx.root):
            steps += [
                Step("install git for the overlay sync",
                     desktop.emerge_tool_argv("dev-vcs/git")),
                Step("sync the Amphitheater overlay", desktop.sync_overlay_argv()),
            ]
        steps.append(Step("emerge the HeDE desktop",
                          desktop.emerge_desktop_argv(binary_only=False)))
        return steps

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return not ctx.plan.desktop or ctx.state.done(self.key)


class CleanupDesktopBinpkgs(ArgvStep):
    """Remove the transient ``@installed`` binpkgs from the target (``plan.desktop``).

    Host-side: ``ProvisionDesktop`` wrote a few GB of binpkgs into the target's
    pkgdir purely so ``InstallDesktop`` could install offline; drop them so a fresh
    install isn't bloated.
    """

    label = "Clean up desktop binpkgs"
    phase = Phase.BASE_SYSTEM
    target_aware = True
    key = "cleanup_desktop_binpkgs"

    def build(self, ctx: InstallContext) -> list[Step]:
        if not ctx.plan.desktop:
            return []
        return [Step("remove transient binpkgs", desktop.cleanup_pkgdir_argv(root=ctx.root))]

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return not ctx.plan.desktop or ctx.state.done(self.key)


class EnableDesktopSession(FuncStep):
    """Boot the installed system into HeDE (``plan.desktop``): write greetd's
    autologin config for the created user (root if none), enable greetd, and switch
    systemd's default target to graphical. No-op for a base-Gentoo install.

    Runs late (FINISH) — after the desktop is installed and the user exists.
    ``systemctl enable`` / ``set-default`` in the chroot are offline filesystem ops
    (symlinks), so they need no running systemd.
    """

    label = "Enable the Helm Desktop Environment session"
    phase = Phase.FINISH
    target_aware = True
    key = "enable_desktop_session"

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        if not ctx.plan.desktop:
            return
        # Autologin the first admin account (fall back to the first account, then
        # root) — a desktop needs someone to land on the session.
        admins = [u.name for u in ctx.plan.users if u.wheel]
        others = [u.name for u in ctx.plan.users]
        user = admins[0] if admins else others[0] if others else "root"
        path = write_under_root(
            ctx.root, desktop.GREETD_CONFIG, desktop.greetd_autologin_config(user))
        _emit(on_progress, f"wrote {path}")
        await run_steps([
            Step("enable greetd", ["systemctl", "enable", "greetd"]),
            Step("boot to graphical", ["systemctl", "set-default", "graphical.target"]),
        ], ctx.target, on_progress=on_progress)
        ctx.state.mark(self)

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return not ctx.plan.desktop or ctx.state.done(self.key)


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
        # Enable the locale in /etc/locale.gen so GenerateLocale can compile it — a
        # fresh stage3 only has C/POSIX/C.UTF-8, so LANG=en_US.UTF-8 would otherwise
        # fall back to C at runtime. Built-ins (C.UTF-8) need no entry.
        gen = sys_locale.locale_gen_line(lang)
        if gen:
            write_under_root(ctx.root, "/etc/locale.gen", gen + "\n")
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


class GenerateLocale(ArgvStep):
    """``locale-gen`` in the target — compile the locale SetTimezoneLocale enabled
    in /etc/locale.gen, so the chosen LANG actually exists at runtime instead of
    falling back to C. Idempotent (a no-op when only built-ins are enabled)."""

    label = "Generate the locale"
    phase = Phase.CONFIGURE
    chroot = True
    key = "generate_locale"

    def build(self, ctx: InstallContext) -> list[Step]:
        return [Step("locale-gen", ["locale-gen"])]

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return ctx.state.done(self.key)


class SetHostname(FuncStep):
    """Set the hostname for both inits: systemd ``/etc/hostname`` + OpenRC
    ``/etc/conf.d/hostname``. The target is systemd by default (reads
    ``/etc/hostname``); the OpenRC file keeps a plain-Gentoo install correct too."""

    label = "Set the hostname"
    phase = Phase.CONFIGURE
    target_aware = True

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        name = ctx.plan.hostname
        if not sys_hostname.valid_hostname(name):
            raise ValueError(f"invalid hostname: {name!r}")
        write_under_root(ctx.root, "/etc/hostname", f"{name}\n")            # systemd
        path = write_under_root(ctx.root, "/etc/conf.d/hostname", f'hostname="{name}"\n')  # OpenRC
        _emit(on_progress, f"wrote /etc/hostname + {path}")

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        try:
            with open(rootpath.resolve(ctx.root, "/etc/hostname"), encoding="utf-8") as fh:
                if fh.read().strip() != ctx.plan.hostname:
                    return False
            with open(rootpath.resolve(ctx.root, "/etc/conf.d/hostname"), encoding="utf-8") as fh:
                return sys_hostname.parse_conf_hostname(fh.read()) == ctx.plan.hostname
        except OSError:
            return False


class SetConsole(FuncStep):
    """Set the console keymap for both inits: systemd ``/etc/vconsole.conf``
    (``KEYMAP=``) + OpenRC ``/etc/conf.d/keymaps`` (upserted, preserving the file).
    systemd (the default target) reads vconsole.conf."""

    label = "Set the console keymap"
    phase = Phase.CONFIGURE
    target_aware = True

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        keymap = ctx.plan.keymap
        if not sys_console.valid_keymap(keymap):
            raise ValueError(f"invalid keymap: {keymap!r}")
        # systemd: vconsole.conf KEYMAP= (a fresh stage3 has none, so write it fresh)
        write_under_root(ctx.root, "/etc/vconsole.conf", f"KEYMAP={keymap}\n")
        # OpenRC: upsert into keymaps, preserving any other keys
        path = rootpath.resolve(ctx.root, sys_console.KEYMAPS_CONF)
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            text = ""
        rendered = sys_console.set_conf_value(text, "keymap", keymap)
        written = write_under_root(ctx.root, sys_console.KEYMAPS_CONF, rendered)
        _emit(on_progress, f"wrote /etc/vconsole.conf + {written}")

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        path = rootpath.resolve(ctx.root, sys_console.KEYMAPS_CONF)
        try:
            with open(path, encoding="utf-8") as fh:
                return sys_console.parse_conf_value(fh.read(), "keymap") == ctx.plan.keymap
        except OSError:
            return False


# --- phase 4: kernel & boot -------------------------------------------------

class InstallKernelSources(ArgvStep):
    """Emerge kernel sources + point ``/usr/src/linux`` at them, before the build.

    A fresh stage3 ships no kernel sources, so ``make``/``genkernel`` (which build
    against ``/usr/src/linux``) would fail. Emerge ``sys-kernel/gentoo-sources`` and
    ``eselect kernel set 1`` to create the symlink. (A binary dist-kernel would skip
    this, but GeSI builds from source.)
    """

    label = "Install kernel sources"
    phase = Phase.KERNEL_BOOT
    chroot = True
    key = "install_kernel_sources"

    def build(self, ctx: InstallContext) -> list[Step]:
        steps = [
            Step("emerge gentoo-sources", _emerge_argv(ctx.plan, "sys-kernel/gentoo-sources")),
        ]
        if ctx.plan.kernel.method == "genkernel":
            # A fresh stage3/@world has no genkernel; the build step needs it. genkernel
            # pulls sys-kernel/linux-firmware via its default +firmware USE — fine under
            # Redistributable/Full (ACCEPT_LICENSE covers @BINARY-REDISTRIBUTABLE), but
            # under Libre (@FREE) that firmware is license-masked and the emerge dies.
            # Build genkernel WITHOUT firmware there (a firmware-free kernel, matching
            # the libre choice) instead of hard-failing on a masked package.
            gk_env = {"USE": "-firmware"} if ctx.plan.license == "libre" else None
            steps.append(Step("emerge genkernel",
                              _emerge_argv(ctx.plan, "sys-kernel/genkernel", env=gk_env)))
        steps.append(Step("select /usr/src/linux", set_argv("kernel", 1)))
        return steps

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return ctx.state.done(self.key)


class StageKernelConfig(FuncStep):
    """Write the curated per-arch kernel config into the target for genkernel.

    Runs host-side (writes into the target root) before ``BuildKernel``. A no-op
    unless ``plan.kernel.kernel_config`` is set (genkernel method + a config is
    bundled for the arch — see ``gest.core.kernel.config``); genkernel's default
    config lacks virtio etc., so a VM install couldn't otherwise find its root.
    """

    label = "Stage the kernel config"
    phase = Phase.KERNEL_BOOT
    target_aware = True          # writes into the target root from the live host
    key = "stage_kernel_config"

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        cfg = ctx.plan.kernel.kernel_config
        if not cfg:
            return
        data = kconfig.bundled_config(ctx.plan.arch)
        if data is None:            # assemble only sets cfg when one exists; belt-and-suspenders
            return
        path = write_under_root(ctx.root, cfg, data.decode("utf-8"))
        _emit(on_progress, f"staged the {ctx.plan.arch} kernel config → {path}")
        ctx.state.mark(self)

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return not ctx.plan.kernel.kernel_config or ctx.state.done(self.key)


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


class InstallGpuDrivers(FuncStep):
    """Install firmware (always) + the NVIDIA proprietary driver (when requested).

    A fresh stage3 ships no ``sys-kernel/linux-firmware``, so hardware needing
    firmware (NVIDIA GSP, most Wi-Fi) has none on the installed system. This step
    always installs it. When ``plan.gpu.nvidia_proprietary`` is set it also accepts
    ``NVIDIA-r2``, emerges ``x11-drivers/nvidia-drivers`` (its out-of-tree module
    builds against the just-built kernel), rebuilds ``@module-rebuild``, and drops a
    modprobe.d file enabling ``nvidia_drm`` KMS + blacklisting nouveau — what a
    Wayland/HeDE desktop needs on a modern GeForce card. Runs after ``BuildKernel``
    (so the module has a kernel) and before ``InstallBootloader``.

    Config writes (``package.license``, ``modprobe.d``) go through the host-side
    root seam; the emerges run in the target's chroot.
    """

    label = "Install GPU drivers & firmware"
    phase = Phase.KERNEL_BOOT
    target_aware = True          # writes package.license + modprobe.d under the root
    key = "install_gpu_drivers"

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        spec = ctx.plan.gpu
        if ctx.plan.license == "libre":
            # Libre (@FREE) forbids linux-firmware and the NVIDIA driver. Skip them
            # rather than license-mask and abort: the system runs on the in-tree
            # drivers (nouveau/amdgpu/i915) with no proprietary firmware — the free-only
            # choice, honoured instead of a hard failure.
            _emit(on_progress, "Libre license — skipping firmware + proprietary drivers")
            ctx.state.mark(self)
            return
        # Accept the licenses the driver/firmware atoms need BEFORE emerging them,
        # else the emerge is license-masked (linux-fw-redistributable / NVIDIA-r2).
        lic = write_under_root(ctx.root, gpu.PACKAGE_LICENSE, gpu.package_license(spec))
        _emit(on_progress, f"wrote {lic}")
        # USE flags (e.g. nvidia-drivers[kernel-open]) must be set before the emerge.
        use = gpu.package_use(spec)
        if use:
            up = write_under_root(ctx.root, gpu.PACKAGE_USE, use)
            _emit(on_progress, f"wrote {up} (nvidia-drivers[kernel-open])")
        # A legacy NVIDIA slot (Kepler 0/470, Fermi 0/390) is masked by the profile —
        # unmask it before the emerge, else the driver atom is mask-blocked.
        unmask = gpu.package_unmask(spec)
        if unmask:
            un = write_under_root(ctx.root, gpu.PACKAGE_UNMASK, unmask)
            _emit(on_progress, f"wrote {un} (legacy nvidia-drivers:{spec.nvidia_slot})")
        steps = [Step(f"emerge {atom}", _emerge_argv(ctx.plan, atom))
                 for atom in gpu.driver_atoms(spec)]
        if spec.nvidia_proprietary:
            # NOT --noreplace: rebuild the module against the freshly built kernel.
            steps.append(Step("rebuild external kernel modules",
                              ["emerge", "--color", "n", "@module-rebuild"]))
        await run_steps(steps, ctx.target, on_progress=on_progress)
        if spec.nvidia_proprietary:
            path = write_under_root(ctx.root, gpu.MODPROBE_CONF, gpu.modprobe_conf())
            _emit(on_progress, f"wrote {path} (nvidia_drm KMS + nouveau blacklist)")
        # Also put the blacklist + modeset on the kernel cmdline: genkernel built the
        # initramfs before this step, so a modprobe.d file alone can't stop nouveau
        # binding during early boot. Merged into /etc/default/grub now, before
        # InstallBootloader runs grub-mkconfig. (No-op for non-NVIDIA GPUs.)
        if gpu.kernel_cmdline(spec):
            grub_path = "/etc/default/grub"
            existing = ""
            try:
                with open(rootpath.resolve(ctx.root, grub_path), encoding="utf-8") as fh:
                    existing = fh.read()
            except OSError:
                pass
            gp = write_under_root(ctx.root, grub_path, gpu.apply_gpu_cmdline(existing, spec))
            _emit(on_progress, f"wrote {gp} (nouveau blacklist + nvidia_drm.modeset cmdline)")
        ctx.state.mark(self)

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
        # A fresh stage3/@world ships no bootloader, so grub-install/grub-mkconfig
        # would fail (exit 127). Emerge GRUB (+ efibootmgr for the UEFI NVRAM entry)
        # first, building the platform grub-install needs (efi-64 / pc).
        uefi = ctx.plan.bootloader.firmware == "uefi"
        atoms = ["sys-boot/grub"] + (["sys-boot/efibootmgr"] if uefi else [])
        steps = [Step("emerge the bootloader", _emerge_argv(
            ctx.plan, *atoms, env={"GRUB_PLATFORMS": "efi-64" if uefi else "pc"}))]
        steps.extend(install_steps(ctx.plan.bootloader, arch=ctx.plan.arch))
        return steps

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return ctx.state.done(self.key)


class InstallBootStub(ArgvStep):
    """Write the Apple Silicon (Asahi) m1n1 + U-Boot boot stub (``update-m1n1``).

    The stage *before* GRUB in the Asahi boot chain (iBoot → m1n1 → U-Boot → GRUB).
    Arch-gated: on anything but arm64 this no-ops (empty pipeline, satisfied), so it
    is inert on x86 while still living at its correct place in the fixed step list.
    """

    label = "Install the m1n1 boot stub"
    phase = Phase.KERNEL_BOOT
    chroot = True
    target_aware = True          # writes into the mounted ESP (efi_directory)
    key = "install_boot_stub"

    def build(self, ctx: InstallContext) -> list[Step]:
        if ctx.plan.arch != "arm64":
            return []
        boot_bin = m1n1.default_boot_bin(ctx.plan.bootloader.efi_directory)
        return [Step("write m1n1 boot stub", m1n1.update_m1n1_argv(boot_bin))]

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        if ctx.plan.arch != "arm64":
            return True          # nothing to do off Apple Silicon
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
    """Create the non-root accounts and add each admin one to ``wheel``."""

    label = "Create user accounts"
    phase = Phase.USERS_NETWORK
    chroot = True

    def build(self, ctx: InstallContext) -> list[Step]:
        steps: list[Step] = []
        for user in ctx.plan.users:
            steps.append(Step(f"create user {user.name}",
                         useradd_argv(user.name, comment=user.comment, shell=user.shell)))
            if user.wheel:
                steps.append(Step(f"add {user.name} to wheel",
                                  gpasswd_argv("wheel", user.name, add=True)))
            if ctx.plan.desktop:
                # A desktop autologin user needs GPU/input/audio access. systemd-logind
                # grants it to the active session via seat ACLs, but the conventional
                # groups are belt-and-suspenders (and needed if a compositor probes them
                # directly). Best-effort per group so one the profile didn't create can't
                # fail the install.
                steps.append(Step(f"add {user.name} to the desktop device groups", [
                    "sh", "-c",
                    'for g in video input audio render; do getent group "$g" '
                    f'>/dev/null && gpasswd -a {user.name} "$g"; done']))
        return steps

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        if not ctx.plan.users:
            return True
        path = rootpath.resolve(ctx.root, "/etc/passwd")
        try:
            with open(path, encoding="utf-8") as fh:
                names = {line.split(":", 1)[0] for line in fh}
        except OSError:
            return False
        return all(u.name in names for u in ctx.plan.users)


class SetUserPassword(ArgvStep):
    """Set each account's password via ``chpasswd`` inside the target.

    Mirrors :class:`SetRootPassword` — passwords are NOT in the plan; each rides a
    run-time callable in :attr:`secrets` (keyed by user name), fed to ``chpasswd``
    on stdin so it never lands in argv or a log. Runs after ``CreateUser``.
    """

    label = "Set user passwords"
    phase = Phase.USERS_NETWORK
    chroot = True

    def __init__(self) -> None:
        #: dict[str, Callable[[], str]] — password callable per user name; set by
        #: the caller (build_registry) before the step runs.
        self.secrets: dict[str, object] = {}

    def build(self, ctx: InstallContext) -> list[Step]:
        steps: list[Step] = []
        for user in ctx.plan.users:
            if not user.set_password:
                continue
            secret = self.secrets.get(user.name)
            if secret is None:
                raise ValueError(f"no password secret supplied for user {user.name!r}")
            argv, stdin = chpasswd_input(user.name, secret())
            steps.append(Step(f"set {user.name}'s password", argv, stdin=stdin))
        return steps

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return not any(u.set_password for u in ctx.plan.users)


class ConfigureNetwork(FuncStep):
    """Give the installed **systemd** system a working network + /etc/hosts.

    The old netifrc ``/etc/conf.d/net`` is inert under systemd, so the machine
    booted with no link. A desktop gets **NetworkManager** (the project's standard;
    GUI/nm-applet); a headless/base system gets built-in **systemd-networkd +
    systemd-resolved**. Both bring up DHCP (or the requested static address) and
    DNS. Also writes /etc/hosts with the machine's own name.
    """

    label = "Configure the network"
    phase = Phase.USERS_NETWORK
    target_aware = True
    key = "configure_network"

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        net = ctx.plan.network
        static = bool(net.interface) and not net.dhcp
        if static:
            if not netifrc.valid_address(net.address):
                raise ValueError(f"invalid interface address: {net.address!r}")
            if not netifrc.valid_gateway(net.gateway):
                raise ValueError(f"invalid gateway: {net.gateway!r}")

        # The machine's own name resolvable before the network is up.
        write_under_root(ctx.root, "/etc/hosts",
                         net_hosts.render_hosts(net_hosts.default_hosts(ctx.plan.hostname)))

        steps = (self._networkmanager(ctx, net, static) if ctx.plan.desktop
                 else self._networkd(ctx, net, static))
        await run_steps(steps, ctx.target, on_progress=on_progress)
        _emit(on_progress, "network configured ("
              + ("NetworkManager" if ctx.plan.desktop else "systemd-networkd") + ")")
        ctx.state.mark(self)

    def _networkmanager(self, ctx, net, static) -> list:
        # NetworkManager auto-connects wired links via DHCP with no config; a static
        # request gets a keyfile connection (mode 0600 — NM refuses world-readable).
        if static:
            iface = net.interface
            conn = ("[connection]\n"
                    f"id={iface}\ntype=ethernet\ninterface-name={iface}\n\n"
                    "[ipv4]\nmethod=manual\n"
                    f"address1={net.address},{net.gateway}\n"
                    + ("dns=" + ";".join(net.nameservers) + ";\n" if net.nameservers else "")
                    + "\n[ipv6]\nmethod=auto\n")
            p = write_under_root(
                ctx.root, f"/etc/NetworkManager/system-connections/{iface}.nmconnection", conn)
            with contextlib.suppress(OSError):
                os.chmod(p, 0o600)
        return [
            Step("emerge NetworkManager", _emerge_argv(ctx.plan, "net-misc/networkmanager")),
            Step("enable NetworkManager", ["systemctl", "enable", "NetworkManager"]),
        ]

    def _networkd(self, ctx, net, static) -> list:
        # Built into systemd — no emerge. resolv.conf → the resolved stub so DNS works.
        if static:
            body = (f"[Match]\nName={net.interface}\n\n[Network]\n"
                    f"Address={net.address}\nGateway={net.gateway}\n"
                    + "".join(f"DNS={s}\n" for s in net.nameservers))
        else:
            body = "[Match]\nName=en* eth*\n\n[Network]\nDHCP=yes\n"
        write_under_root(ctx.root, "/etc/systemd/network/20-gest.network", body)
        link = rootpath.resolve(ctx.root, "/etc/resolv.conf")
        os.makedirs(os.path.dirname(link), exist_ok=True)
        with contextlib.suppress(OSError):
            os.remove(link)
        os.symlink("/run/systemd/resolve/stub-resolv.conf", link)
        return [
            Step("enable systemd-networkd", ["systemctl", "enable", "systemd-networkd"]),
            Step("enable systemd-resolved", ["systemctl", "enable", "systemd-resolved"]),
        ]

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return ctx.state.done(self.key)


# --- phase 6: finish (tier-2 opt-in) ----------------------------------------

class WriteConfigStep(FuncStep):
    """Render a module's config and write it under the target root (seam).

    ``target_aware`` and host-side: the target isn't running, so no live command
    (the write is the whole effect; the service picks it up on first boot).
    """

    phase = Phase.FINISH
    target_aware = True

    def __init__(self, label: str, abs_path: str,
                 render: Callable[[], str], *, mode: int = 0o644) -> None:
        self.label = label
        self._abs_path = abs_path
        self._render = render
        self._mode = mode

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None = None) -> None:
        path = write_under_root(ctx.root, self._abs_path, self._render(), mode=self._mode)
        _emit(on_progress, f"wrote {path}")

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return os.path.exists(rootpath.resolve(ctx.root, self._abs_path))


class ChrootCmdStep(ArgvStep):
    """Run one command inside the target (emerge a package, enable a service)."""

    phase = Phase.FINISH
    chroot = True

    def __init__(self, label: str, key: str, argv: list[str]) -> None:
        self.label = label
        self.key = key
        self._argv = argv

    def build(self, ctx: InstallContext) -> list[Step]:
        return [Step(self.label, self._argv)]

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return ctx.state.done(self.key)


def _emerge_argv(plan: InstallPlan, *atoms: str,
                 env: dict[str, str] | None = None) -> list[str]:
    """`emerge` one or more atoms in-chroot: --noreplace so an already-present
    package is a quick no-op; --getbinpkg when the plan prefers binaries. ``env``
    prepends ``env KEY=VALUE …`` (e.g. USE / GRUB_PLATFORMS for a single emerge)."""
    argv = ["emerge", "--color", "n", "--noreplace"]
    if plan.binary_pref:
        argv.insert(1, "--getbinpkg")
    argv = [*argv, *atoms]
    if env:
        argv = ["env", *(f"{k}={v}" for k, v in env.items()), *argv]
    return argv


# Sensible install-time defaults for the opt-in day-2 modules.
def _default_firewall() -> FirewallPolicy:
    # Locked down, but keep SSH reachable — the common server default.
    return FirewallPolicy(default_input="drop", allow_ping=True, tcp_ports=[22], udp_ports=[])


def _default_sysctl() -> dict[str, str]:
    return {"net.ipv4.tcp_syncookies": "1", "kernel.kptr_restrict": "1"}


def _tier2_module_steps(plan: InstallPlan, key: str) -> list[InstallStep]:
    """The steps for one opt-in day-2 module (config + package + service enable)."""
    if key == "sshd":
        return [
            ChrootCmdStep("Emerge openssh", "tier2_openssh",
                          _emerge_argv(plan, "net-misc/openssh")),
            WriteConfigStep("Configure sshd", SSHD_CONFIG,
                            lambda: sshd_config.apply_settings("", SshdSettings())),
            ChrootCmdStep("Enable sshd at boot", "tier2_sshd_enable",
                          ["systemctl", "enable", "sshd"]),
        ]
    if key == "firewall":
        return [
            ChrootCmdStep("Emerge nftables", "tier2_nftables",
                          _emerge_argv(plan, "net-firewall/nftables")),
            # systemd's nftables.service loads /etc/nftables.conf — NOT the OpenRC
            # default (fw_nft.NFT_PATH = /etc/nftables.nft), which it would ignore,
            # leaving the enabled firewall empty. The target is systemd.
            WriteConfigStep("Configure the firewall", "/etc/nftables.conf",
                            lambda: fw_nft.render_ruleset(_default_firewall())),
            ChrootCmdStep("Enable nftables at boot", "tier2_nftables_enable",
                          ["systemctl", "enable", "nftables"]),
        ]
    if key == "sudo":
        return [
            ChrootCmdStep("Emerge sudo", "tier2_sudo", _emerge_argv(plan, "app-admin/sudo")),
            WriteConfigStep("Configure sudo (wheel)", SUDOERS_DROPIN,
                            lambda: priv_render.render_sudoers(
                                EscalationPolicy("sudo", group="wheel")),
                            mode=0o440),
        ]
    if key == "sysctl":
        return [
            WriteConfigStep("Configure sysctl", SYSCTL_DROPIN,
                            lambda: sysctl_config.render_conf(_default_sysctl())),
        ]
    raise ValueError(f"unknown tier-2 module: {key!r}")


# The order tier-2 modules expand in (phase 6), and the set of known keys.
TIER2_MODULES = ("sshd", "firewall", "sudo", "sysctl")


def _tier2_steps(plan: InstallPlan) -> list[InstallStep]:
    """Expand ``plan.tier2`` (row 19) into opt-in day-2 steps — empty by default.

    Each selected module writes its config into the target (via the seam) and, for
    the service modules, emerges its package and enables the service in the chroot.
    An unknown key is refused loudly rather than silently skipped.
    """
    unknown = set(plan.tier2) - set(TIER2_MODULES)
    if unknown:
        raise ValueError(f"unknown tier-2 modules: {', '.join(sorted(unknown))}")
    steps: list[InstallStep] = []
    for key in TIER2_MODULES:
        if key in plan.tier2:
            steps.extend(_tier2_module_steps(plan, key))
    return steps


Secret = Callable[[], str]


def _root_password_step(root_secret: Secret | None) -> SetRootPassword:
    """A ``SetRootPassword`` with its run-time secret callable wired in (if given)."""
    step = SetRootPassword()
    if root_secret is not None:
        step.secret = root_secret
    return step


def _user_password_step(user_secrets: dict[str, Secret] | None) -> SetUserPassword:
    """A ``SetUserPassword`` with its per-user secret callables wired in (if given)."""
    step = SetUserPassword()
    if user_secrets:
        step.secrets = dict(user_secrets)
    return step


def _admin_model_steps(plan: InstallPlan) -> list[InstallStep]:
    """Escalation + root-lock steps for the admin model (empty for *traditional*).

    Runs after ``CreateUser`` so the wheel user exists before root is ever locked —
    the "never ship a system you can't administer" invariant (gesi-account-model).
    *sudo-augmented* adds the escalator rule (root still has a password);
    *rootless* adds it AND locks the root account (``passwd -l root``).
    """
    model = plan.admin_model
    if model == "traditional":
        return []
    steps: list[InstallStep] = []
    if installs_escalator(model):
        if plan.escalator == "doas":
            steps.append(ChrootCmdStep("Emerge doas", "admin_doas",
                                       _emerge_argv(plan, "app-admin/doas")))
            steps.append(WriteConfigStep(
                "Configure doas (wheel)", DOAS_CONF,
                lambda: priv_render.render_doas_block(EscalationPolicy("doas", group="wheel")),
                mode=0o400))
        else:
            steps.append(ChrootCmdStep("Emerge sudo", "admin_sudo",
                                       _emerge_argv(plan, "app-admin/sudo")))
            steps.append(WriteConfigStep(
                "Configure sudo (wheel)", SUDOERS_DROPIN,
                lambda: priv_render.render_sudoers(EscalationPolicy("sudo", group="wheel")),
                mode=0o440))
    if model == "rootless":
        # Last, and only after the escalator + wheel user are in place.
        steps.append(ChrootCmdStep("Lock the root account", "admin_lock_root",
                                   ["passwd", "-l", "root"]))
    return steps


class ConfigureClock(ArgvStep):
    """Set the target's clock policy (plan.clock): RTC convention + NTP.

    chrony → RTC in UTC, systemd-timesyncd off, chrony emerged + chronyd enabled.
    local  → RTC in local time (/etc/adjtime LOCAL), no NTP daemon (dual-boot style).
    """

    label = "Configure the clock"
    phase = Phase.FINISH
    chroot = True
    key = "configure_clock"

    def build(self, ctx: InstallContext) -> list[Step]:
        conv = "LOCAL" if ctx.plan.clock == "local" else "UTC"
        steps = [
            Step("set the RTC convention",
                 ["sh", "-c", f"printf '0.0 0 0.0\\n0\\n{conv}\\n' > /etc/adjtime"]),
            Step("disable systemd-timesyncd",
                 ["sh", "-c", "systemctl disable systemd-timesyncd 2>/dev/null || true"]),
        ]
        if ctx.plan.clock == "chrony":
            steps.append(Step("emerge chrony", _emerge_argv(ctx.plan, "net-misc/chrony")))
            steps.append(Step("enable chronyd at boot", ["systemctl", "enable", "chronyd"]))
        return steps

    async def is_satisfied(self, ctx: InstallContext) -> bool:
        return ctx.state.done(self.key)


def build_registry(plan: InstallPlan, *, root_secret: Secret | None = None,
                   user_secrets: dict[str, Secret] | None = None) -> list[InstallStep]:
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
        # HeDE desktop (no-op for base Gentoo): provision binpkgs+overlay, emerge, clean up
        ProvisionDesktop(),
        InstallDesktop(),
        CleanupDesktopBinpkgs(),
        SetTimezoneLocale(),
        GenerateLocale(),
        SetHostname(),
        SetConsole(),
        InstallKernelSources(),
        StageKernelConfig(),
        BuildKernel(),
        InstallGpuDrivers(),        # firmware always; NVIDIA proprietary when requested
        InstallBootloader(),
        InstallBootStub(),          # arm64/Asahi only; no-op on x86
        _root_password_step(root_secret),
        CreateUser(),
        _user_password_step(user_secrets),
        ConfigureNetwork(),
        EnableDesktopSession(),     # boot into HeDE (no-op for base Gentoo)
        ConfigureClock(),           # RTC convention + chrony/local NTP policy
    ]
    # Admin model (escalator + rootless root-lock); empty for traditional, so the
    # default registry is byte-identical. FINISH phase, after the user exists.
    steps.extend(_admin_model_steps(plan))
    steps.extend(_tier2_steps(plan))
    return steps


def build_minimal_registry(
    plan: InstallPlan, *, root_secret: Secret | None = None
) -> list[InstallStep]:
    """The smallest ordered set of steps that produces a *bootable* system (§9c).

    A strict subset of :func:`build_registry`: the boot-critical path only —
    partition → mount → stage3 → fstab → make.conf → prepare-chroot → sync →
    profile → @world → kernel → bootloader → (arm64: m1n1 boot stub) → root
    password. It drops the
    day-1-nicety config steps (timezone/locale, hostname, console keymap) and the
    optional user, network and tier-2 steps; those layer back in via
    :func:`build_registry`. The installed system boots to a root login; the rest
    is configured on first boot or a fuller run.

    It also drops the HeDE desktop step, so callers must pass a *base* plan
    (``desktop=False`` → ``seamless`` gated off): a seamless plan here would set
    ``kernel.plymouth`` without the desktop having installed plymouth, and the
    ``genkernel --plymouth`` build would fail. ``assemble_plan`` couples the two,
    so an assembled base-Gentoo plan is safe.
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
        InstallKernelSources(),
        StageKernelConfig(),
        BuildKernel(),
        InstallBootloader(),
        InstallBootStub(),          # arm64/Asahi only; no-op on x86 — boot-critical there
        _root_password_step(root_secret),
    ]
