# Design: the system installer (orchestration over the modules)

*Status: proposal · Target: new `gest/core/install/` + `gest/core/stage3/` + small `gest/core/exec/` extension · Depends on: [module-foundation](module-foundation.md) (Tier 1 + Tier 2, now complete), [runtime-privilege-path](runtime-privilege-path.md), [storage-provisioning](storage-provisioning.md) · Milestone: the next track after the foundation*

## Why this is orchestration, not a new program

The module-foundation roadmap made the wager explicit: an installer is **not a new
subsystem**, it is a flow that points the modules GeST already uses to administer a
running system at a **target root under `/mnt/gentoo`**, sequenced in Gentoo
Handbook order. The foundation exists precisely so this track is thin. Every install
step is an operation a module already performs; the installer's job is to order them,
thread a root through them, and stream the result.

Concretely, the Handbook install maps onto the existing surface almost one-to-one.
"Changes with a target root" is the whole design problem, isolated to one column:

| Handbook step | Module / file | Method(s) | What changes with a target root |
|---|---|---|---|
| Partition the disk | `core/disk/provision.py` | `uefi_plan`, `apply_plan` / `apply_via_backend` | Nothing — operates on device args; already root-agnostic |
| Make filesystems + swap | `core/disk/provision.py` | `plan_steps` (`mkfs.*`/`mkswap`/`swapon`) | Nothing — device args |
| Mount the target | `core/disk/mount.py` | `derive_mount_plan`, `apply_mount_plan` | Already target-aware (`MountPlan.root`, confined to `/mnt|/media|/run/media`) |
| **Stage3 tarball** | **NEW `core/stage3/`** | download + verify + unpack | Unpacks into `root`; genuinely new (see below) |
| Generate `/etc/fstab` | `core/disk/mount.py` | `generate_target_fstab`, `write_target_fstab_file` | Already target-aware (writes `<root>/etc/fstab`) |
| `make.conf` / USE / keywords | `core/portage/*` via `PortageService` | `paths.make_conf(root)`, `WriteConfig` | Already root-aware — `paths.py` honours `PORTAGE_CONFIGROOT` and every path fn takes `root` |
| repos / mirrors / binhost | `core/repos`, `core/software` | `SyncRepos`, `Sync` | `repos.conf`/`binrepos.conf` under `root`; sync runs in chroot |
| Sync the Portage tree | `core/software` | `Sync` (`emerge --sync`) | Runs in chroot (tree lives in the target) |
| Base system / `@world` | `core/software` via `SoftwareService` | `UpdateWorld`, `InstallMulti`, `InstallBinaryMulti` | `emerge -uDN @world` run in chroot |
| Timezone / locale / hostname | `core/system/{timezone,locale,hostname}.py` | writers + `SystemService` | Writer resolves its file under `root` (seam) |
| Console keymap / font | `core/system/console.py` | `set_conf_value`, `SetKeymap`/`SetConsoleFont` | Writer resolves `/etc/conf.d/keymaps` under `root` (seam) |
| Kernel build | `core/kernel/build.py` via `KernelService` | `build_steps`, `build` | Runs in chroot (`make`/`genkernel` on the target's `/usr/src/linux`) |
| Bootloader install | `core/bootloader/install.py` | `install_steps`, `install` | Partly seamed (`InstallConfig.boot_directory`); `grub-mkconfig` runs in chroot |
| Root password + user | `core/users/commands.py` via `UsersService` | `chpasswd_input`, `useradd_argv`, `gpasswd_argv` | Run in chroot (writes the target's `/etc/{passwd,shadow}`) |
| Network (wired) | `core/network/netifrc.py` | `parse_conf_net` + writer | Writer resolves `/etc/conf.d/net` under `root` (seam) |
| DNS + hosts | `core/network/{resolv,hosts}.py` | `render_resolv`, `render_hosts`, `default_hosts` | Writer resolves under `root` (seam) |
| Wi-Fi | `core/wifi/` via `WifiService` | `AddNetwork` | Config under `root` (seam); optional |
| sshd / firewall / sudo-doas / sysctl | `core/{sshd,firewall,privilege,sysctl}` | `ApplyConfig` / `ApplyPolicy` / `SetSudo`/`SetDoas` / `ApplySettings` | Writer resolves under `root` (seam); day-2, optional during install |

Two rows are genuinely new (`stage3`, and the chroot plumbing the "runs in chroot"
rows imply). Everything else is an existing method plus a root argument. That is the
thesis: **the foundation work and the installer's prerequisites are the same work.**

## The target-root seam — the central design problem

The roadmap's instruction is "thread a target root through paths, not logic." The
codebase already proves the pattern in three places; the installer generalises it.
There are two categories of module, and they take a root differently.

### File-writing modules (system, network, sshd, privilege, sysctl, envd, fstab, make.conf)

These render a config file and write it. The rule: **a writer resolves its target
path under a configurable root (default `/`).** The reference implementation is
`core/portage/paths.py`, where `config_root()` reads `PORTAGE_CONFIGROOT` and every
path function (`etc_portage(root)`, `make_conf(root)`, `package_fragment(kind, name,
root)`) already accepts an explicit `root`. The disk module does the same for fstab:
`mount.write_target_fstab_file(target_root, text)` writes `<target_root>/etc/fstab`.

The gap is the rest of the file-writing modules, which today hard-code their path
constants — `console.KEYMAPS_CONF = "/etc/conf.d/keymaps"`, `resolv.RESOLV_PATH =
"/etc/resolv.conf"`, `hosts.HOSTS_PATH = "/etc/hosts"`, `hostname`'s
`/etc/conf.d/hostname`, netifrc's `/etc/conf.d/net`, and the Tier-2 drop-ins. The
minimal, uniform change:

- Add one small path-resolution helper (a `core/paths.py` `under_root(root, *parts)`,
  or a per-module `paths.py` mirroring `core/portage/paths.py`) that resolves each
  managed file under a `root` defaulting to `/`. The existing module-level constants
  become the `root == "/"` case, so every current caller is unchanged.
- The backend write RPC for each module grows a `root` (or `target`) argument. It is
  **server-side confined to the `/mnt|/media|/run/media` prefixes** — the exact guard
  `mount.valid_target_root` / `guard_target_root` and the `disk.mounttarget` polkit
  action already enforce — so a target write can never land on the running system.
- Validation and rendering (the pure `render_*`/`valid_*` functions) are untouched;
  only the resolved output path changes.

This is deliberately mechanical: no module's logic forks for install vs. maintenance,
matching the roadmap's "do not fork provisioning logic" constraint.

### Command-running modules (emerge, kernel build, bootloader, eselect)

These run a tool that must act *inside* the target. Two mechanisms, chosen per tool:

- **Native root flag** where the tool has one. Portage takes `emerge --root=<root>
  --config-root=<root>`; `grub-install` takes `--boot-directory`/`--efi-directory`
  (the `InstallConfig.boot_directory`/`efi_directory` seam already exists). These can
  run from the live CD without a chroot.
- **`chroot <root> …`** where the tool probes or writes the running system: the
  kernel build (`make`/`genkernel` against the target's `/usr/src/linux`),
  `grub-mkconfig` (probes mounts and the running kernel), `eselect profile`, and the
  base-system `@world` merge, which is far simpler and more faithful to the Handbook
  run inside the chroot than juggling `--root` for a full bootstrap.

The Handbook itself chroots for the base-system phase, so the installer's primary
mechanism is chroot, with native root flags used only where they are strictly
simpler (fstab, bootloader target directories).

### How this composes with `core/exec`

The executor abstraction already carries the privilege decision:
`choose_executor()` returns `DirectExecutor` when `os.geteuid() == 0` (the live CD)
and `DBusExecutor` otherwise. **The installer runs on a Gentoo minimal CD as root, so
the `DirectExecutor` path is primary** — the same path the partitioner, kernel build,
and target-mount screens already take (`gest/tui/screens/{partition,kernel,mount_target}.py`
all branch on `isinstance(executor, DirectExecutor)`).

`chroot` requires uid 0, which is exactly the `DirectExecutor` precondition — so the
chroot mechanism composes cleanly with the already-root/direct model and simply is not
available (and not needed) on the unprivileged installed-system path. The chroot
wrapper is therefore a thin transform over the existing `Executor` (see the flow
engine, below), not a new privilege path.

## What is genuinely new (small, enumerated)

Everything below is net-new; it is deliberately little.

1. **Stage3 module** (`core/stage3/`). Select a stage3 variant from a mirror, download
   it, **verify it** (the `.DIGESTS`/sha256 and the GPG signature against the Gentoo
   release keys), and unpack it (`tar xpf … --xattrs-include='*.*' --numeric-owner`)
   into the target root. Split like every other module: a pure reader/parser for the
   mirror's `latest-stage3-*.txt` index and the digest file, pure argv/verification
   helpers, and an apply that streams like emerge (reuse the `runner.stream` /
   `Progress` batching). A new backend interface `org.gentoo.gest.Stage3` with a
   `stage3.unpack` polkit action; on the live CD it runs direct.
2. **Pseudo-filesystem mounts.** Before chroot, mount `/proc` (proc), `/sys` (sysfs),
   `/dev` (rbind), `/dev/pts`, and `/run` (rbind) under the target, and tear them down
   after (critically, on failure too, or the target can't be cleanly unmounted). A
   small extension to `core/disk/mount.py` (it already owns the `MountPlan` pipeline
   and the `/mnt` confinement) or a sibling `core/chroot/prepare.py`.
3. **A chroot-exec helper.** An extension of `core/exec`: given an inner `Executor`
   and a `root`, produce argv `["chroot", root, *argv]`. Modelled as a
   `ChrootExecutor(inner, root)` implementing the `Executor` protocol, so `run_steps`
   and every module apply function are agnostic to whether they run on the host or in
   the target.
4. **DNS copy into the target.** Copy the live CD's `/etc/resolv.conf` to
   `<root>/etc/resolv.conf` so `emerge` can resolve mirrors inside the chroot. One
   step; distinct from the persistent `core/network/resolv.py` config the user chooses
   for the installed system.
5. **The flow engine + its TUI.** An ordered, resumable pipeline where each step
   reports progress — and the installer screen that reviews the plan and streams the
   run (see below).

## The installer flow

Handbook order, grouped into phases. Each step names its module/method, whether it is
already target-root-aware or needs the **seam**, and whether it is **chroot**-run.

**Phase 1 — Prepare disk**
1. Partition — `provision.apply_plan` (root-agnostic).
2. Filesystems + swap — `provision.plan_steps` mkfs/mkswap/swapon (root-agnostic).
3. Mount target — `mount.apply_mount_plan` (target-aware).

**Phase 2 — Base system**
4. Stage3 select + verify + unpack — **NEW** `core/stage3` (unpacks into `root`).
5. Generate + write `/etc/fstab` — `mount.generate_target_fstab` /
   `write_target_fstab_file` (target-aware).
6. `make.conf` / mirrors / binhost — `core/portage` `paths.make_conf(root)`,
   `WriteConfig` (root-aware today).
7. Mount pseudo-filesystems + copy `resolv.conf` — **NEW** (prep for chroot).
8. Sync the Portage tree — `Sync` (**chroot**).
9. Select profile — `eselect profile set` (**chroot**).
10. Emerge base `@world` (`-uDN`, optionally `--getbinpkg`) — `UpdateWorld` /
    `InstallBinaryMulti` (**chroot**).

**Phase 3 — Configure**
11. Timezone / locale — `core/system/{timezone,locale}.py` (**seam**).
12. Hostname — `core/system/hostname.py` (**seam**).
13. Console keymap / font — `core/system/console.py` (**seam**).

**Phase 4 — Kernel & boot**
14. Kernel build (+ initramfs) — `core/kernel/build.build_steps` (**chroot**).
15. Bootloader install + `grub-mkconfig` — `core/bootloader/install.install_steps`
    (`boot_directory` seam for install; **chroot** for mkconfig).

**Phase 5 — Users & network**
16. Root password — `users.chpasswd_input` (**chroot**).
17. Create user + `wheel` — `users.useradd_argv` + `gpasswd_argv` (**chroot**).
18. Wired network — `core/network/netifrc.py` (**seam**); DNS/hosts —
    `resolv`/`hosts` writers (**seam**); Wi-Fi — `core/wifi` (**seam**, optional).

**Phase 6 — Finish (optional day-2, opt-in)**
19. sshd / firewall / sudo-doas / sysctl — `core/{sshd,firewall,privilege,sysctl}`
    (**seam**/**chroot** as each applies). Off by default; a first-boot alternative.
20. Unmount pseudo-filesystems and the target, in reverse order.

## Safety

The installer inherits the partitioner's discipline and adds nothing that relaxes it.

- **Reuse the disk device guards verbatim.** `provision.validate_plan` /
  `guard_provision_target` already refuse a mounted device, the running root, and the
  live medium (`boot_source`). The installer must never operate on the running/live
  medium — it passes the live CD's boot device as `boot_source` so the destructive
  phase cannot target it.
- **Target-root confinement.** Every target write is confined to
  `ALLOWED_TARGET_ROOTS` (`/mnt|/media|/run/media`) by `mount.guard_target_root` and
  the file-writing seam, server-side. A mis-set root can never write `/`.
- **Typed confirmation before the destructive disk phase**, reusing the partitioner's
  current-vs-planned diff preview and typed-device-name confirmation.
- **The whole run is a reviewable plan before execution** — the `DiskPlan` pattern
  lifted to the install: the assembled step list (disk plan, stage3 choice, profile,
  kernel method, bootloader, users, network) is rendered for review and confirmed as a
  unit before anything runs.
- **Idempotency / resumability.** Steps are ordered and labelled; a completed-step
  marker lets a re-run resume rather than repeat (e.g. don't re-unpack stage3 if it is
  present and verified). Pseudo-fs teardown runs on failure so a partial install
  leaves a cleanly unmountable target.

## The flow engine

A small orchestration model, in the spirit of `core/exec/steps.py` but one level up.
`run_steps` runs a flat list of argv `Step`s and stops at the first `StepError`; the
installer needs steps that also call Python module functions (render a config and
write it, verify a tarball) and that group into phases and resume. So **generalise,
don't reuse directly**:

- An `InstallStep`: a label, a phase, a `chroot: bool`/`target_aware: bool` marker,
  and an `async run(ctx, on_progress)` that may call a module core function *or* the
  executor. Pure-argv steps wrap the existing `steps.Step` and go through `run_steps`
  unchanged; richer steps (stage3 verify, config writes) implement `run` directly.
- An `InstallContext` carrying the chosen `root`, the process-wide `Executor` (and its
  `ChrootExecutor` view of the target), the reviewed `DiskPlan`/`MountPlan`, and the
  user's selections.
- **Progress is streamed** exactly like the partition/kernel apply screens: each step
  reports start via an `on_step(index)` callback and lines via `on_progress`, driving a
  `RunScreen`-style per-phase table + progress bar (`gest/tui/screens/runscreen.py`).
- **Failure stops** with a clear, labelled error (the `StepError`/`DiskApplyError`
  shape) and does not proceed; the raw log is viewable, as elsewhere.
- **Resume-from-step**: the engine records the last completed step; a re-run skips
  through already-satisfied steps. Where to persist the marker is an open question
  (below).

## Sequencing

Each item is independently landable and testable in GeST's release cadence, and each
unblocks the next — the same argument that made "modules first" correct.

1. **Target-root seam across the file-writing modules.** Bring `system`, `network`,
   `sshd`, `privilege`, `sysctl`, `envd` in line with `core/portage/paths.py` and the
   fstab writer: a `root`-defaulting path helper + a confined `root` arg on each write
   RPC. Pure path-resolution unit tests; no install needed to verify.
2. **Stage3 module.** Download + verify + unpack, standalone. Testable over fixtures
   (a captured mirror index and a known digest/signature) with no network.
3. **Chroot primitives.** The `ChrootExecutor` helper, the pseudo-fs mount/teardown,
   and the `resolv.conf` copy — one small landable unit that makes "enter the target"
   possible.
4. **Flow engine + minimal end-to-end.** The `InstallStep`/`InstallContext` model and a
   first bootable path: partition → stage3 → fstab → make.conf → chroot → sync →
   profile → `@world` → kernel → bootloader → root password. The smallest install that
   boots.
5. **Installer TUI.** Plan review + typed confirmation + the streamed per-phase run,
   reusing `RunScreen`. This is where the flow becomes usable.
6. **Optional day-2 steps.** Fold the Tier-2 modules (sshd, firewall, sudo/doas,
   sysctl, Wi-Fi) in as opt-in install steps, or leave them for first boot.

**Why this ordering:** step 1 is the seam that makes the whole track "paths not
logic"; it is small and ships value on its own (every module gains a target-root write
it can be tested against). Steps 2–3 are the only genuinely new subsystems and are
isolated and fixture-testable. By step 4 the pieces already exist, so the engine is
thin. The TUI (5) and day-2 (6) are pure additions on a working core.

## Testing

Follow the established patterns; none of these wipe a disk.

- **Step-list / plan tests.** Assert the assembled `InstallStep` list is in Handbook
  order, phases group correctly, and each step's `chroot`/`target_aware` marker is
  right — pure, no execution (the `plan_steps` ordering-assertion pattern).
- **`FakeExecutor`** (from runtime-privilege-path) records the ordered argv the whole
  flow would run — including the `chroot <root>` prefixes — with no subprocess and no
  bus, the same double the partitioner's apply pipeline uses.
- **Target-root path resolution unit tests.** Each file-writing module resolves its
  managed file under an injected `root` (e.g. `/mnt/gentoo/etc/conf.d/hostname`), and
  refuses a root outside the confined prefixes.
- **Stage3 parser/verifier tests over fixtures.** Parse a captured
  `latest-stage3-*.txt`, verify a good `.DIGESTS`/sha256 fixture and reject a tampered
  one; the GPG path is exercised against a fixture keyring.
- **Live-CD manual test path.** The real test, inherited from the partitioner
  (live-CD-on-a-separate-machine): boot a Gentoo minimal CD, GeST runs as root
  (`DirectExecutor` auto-selected), install onto a scratch disk, and reboot into it.

## Non-goals

- **Desktop profile setup beyond the Handbook** — no automatic X/Wayland, display
  manager, or desktop-environment provisioning. The installer produces a bootable base
  system; desktop configuration is day-2.
- **systemd** — OpenRC only, per the project. No systemd stage3 variant, no
  `systemd-*` configuration.
- **A GUI installer** — the Qt/KDE frontend stays gated until the TUI/CLI side is
  declared complete.
- **Tier 3 modules** (printers, sound, bluetooth, etc.) — unrelated to bootstrapping.
- **Automated / unattended (kickstart-style) install** as a first cut — the first
  installer is interactive and reviewed. A declarative install-from-file profile is a
  later possibility, not this milestone.
- **Disk encryption / LVM / RAID.** Verified against the code: LUKS/LVM/RAID have not
  landed — `core/disk` exposes only the `8E00` (LVM) and `FD00` (RAID) type-GUID
  *constants*, no `cryptsetup`/`lvm`/`mdadm` logic. Storage provisioning still defers
  them, so the installer does too; it targets the plain GPT/UEFI layout `uefi_plan`
  builds. They layer on the same modules later, unchanged.
- **MBR/BIOS as the default** — GPT/UEFI first (per the storage doc); BIOS via the
  existing `InstallConfig.firmware = "bios"` path is a follow-on.

## Open questions

1. **Stage3 variant selection.** Offer which of openrc / desktop-openrc / hardened /
   musl? systemd variants are out (non-goal). Proposed default: `stage3-*-openrc`, with
   desktop and hardened as offered alternatives.
2. **Profile selection timing.** Run `eselect profile set` in the chroot *before* the
   base `@world` merge (so USE defaults apply to the build), vs. leave it for first
   boot. Proposed: during install, before `@world`.
3. **Binary vs source base system.** Use `--getbinpkg` (the existing
   `InstallBinaryMulti` path) to speed the base `@world`, or build from source per the
   classic Handbook? Proposed: offer binary-preferred with a source fallback.
4. **How much of Tier 2 runs during install.** sshd/firewall/sudo-doas/sysctl/Wi-Fi as
   opt-in install steps, or always deferred to first boot? Proposed: opt-in, off by
   default.
5. **Existing-partition (no-wipe) install path.** Support installing onto
   already-made partitions the user selects (skip Phase 1's destructive steps, still
   generating fstab from the chosen devices)? A common request; needs its own safety
   review of the "don't wipe, but do mkfs/mount what I picked" case.
6. **Where the resume marker persists.** In the target's `/etc/portage/gest/` via
   `paths.gest_state(name, root)` (survives a reboot but only exists after stage3), or
   a live-session file under `/run`? Proposed: session file until stage3 is unpacked,
   then the target state dir.
7. **Pseudo-fs teardown ownership on abort.** Guarantee unmount-in-reverse on any
   failure so a partial install leaves a cleanly unmountable target — belongs in the
   flow engine's finally-path, not individual steps.
