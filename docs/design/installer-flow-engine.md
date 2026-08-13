# Design: the installer flow engine (step 4 — the pipeline that installs)

*Status: proposal · Scope: new `gest/core/install/` (the `InstallStep`/`InstallContext`/`InstallPlan` types + the step registry + the run loop) · Depends on: [installer](installer.md) (this is the detailed design of its "The flow engine" section and its "Phase 1–6 flow"), the target-root seam (v0.50.11), the stage3 module (v0.50.12), the chroot primitives (v0.50.13) · Defers: the installer TUI (step 5), no-wipe install, unattended install, LUKS/LVM, systemd · Milestone: step 4 — the ordered, resumable, progress-streaming pipeline + a minimal bootable end-to-end*

## Why an engine at all

The three building blocks are in `main`: the file-writing modules take a `root`
(`gest.core.rootpath.resolve`), `ChrootExecutor(inner, root)` runs any argv inside
the target, and `core/stage3` downloads/verifies/unpacks a tarball. What is left is
the *ordering*: sequence twenty operations in Handbook order, hand each the right
executor (host vs. chroot), stream every line, stop cleanly on the first failure, and
tear the pseudo-filesystems down whatever happens. That is the whole job of step 4.

The parent doc already made the wager that the installer is orchestration, not a new
subsystem, so this engine adds no new privileged surface and no new provisioning
logic. It calls existing module functions — `provision.apply_plan`,
`mount.apply_mount_plan`, `mount.write_target_fstab_file`, `prepare_chroot`,
`build_steps`, `install_steps`, `chpasswd_input` — in a fixed order over an
`Executor`. It is deliberately thin: one small model, one registry, one loop.

`core/exec/steps.py` already has the shape one level down — `run_steps` runs a flat
list of argv `Step`s through an `Executor` and stops at the first `StepError`. The
installer needs steps that also call Python module functions (verify a tarball, render
and write a config, derive a plan), that group into phases, that pick host-or-chroot,
and that can be *skipped on a re-run*. So we generalise `run_steps`, we do not reuse it
directly — but every pure-argv step still delegates to it unchanged.

## 1. The `InstallStep` model

An `InstallStep` is a `Protocol` (a couple of concrete base classes implement it):

```python
class InstallStep(Protocol):
    label: str            # human line, like a steps.Step label
    phase: Phase          # PREPARE_DISK | BASE_SYSTEM | CONFIGURE | KERNEL_BOOT | USERS_NETWORK | FINISH
    chroot: bool          # runs inside the target (engine hands it ctx.target)
    target_aware: bool    # writes under root via a seam/native flag (no chroot needed)

    async def run(self, ctx: InstallContext, on_progress: OnProgress | None) -> None: ...
    async def is_satisfied(self, ctx: InstallContext) -> bool: ...
```

- `run` may call a module core function (`mount.apply_mount_plan(plan, executor)`,
  `mount.write_target_fstab_file(root, text)`, `verify.verify_hashes(...)`) *or* the
  executor directly. It raises on failure — `StepError`/`DiskApplyError`/`ValueError`
  — and the engine catches it.
- `is_satisfied(ctx)` lets a re-run skip an already-done step (stage3 already unpacked
  and verified, fstab already present, profile already the chosen one). Default
  `False` for steps that must always re-check, `True`-when-detected for the expensive
  ones.
- `chroot`/`target_aware` are the same two markers `installer.md` already annotates
  each Handbook step with; here they are fields the engine reads to choose the
  executor, not documentation.

Two base classes cover almost everything, so most registry entries are one line:

- **`ArgvStep`** wraps the existing `steps.Step`. Its `run` is
  `run_steps([self.step], executor, on_progress=on_progress)` where `executor` is the
  one the engine selected. This is how every pure-argv operation — mkfs, mount,
  `eselect profile set`, `emerge`, `grub-install`, `chpasswd` — reaches the pipeline
  with zero new machinery. A step that is a whole sub-pipeline (kernel `build_steps`,
  bootloader `install_steps`, the pseudo-fs mounts) is an `ArgvStep`-list variant that
  hands the module's own step list to `run_steps`.
- **`FuncStep`** wraps an `async` callable `(ctx, on_progress) -> None` for the richer
  steps that are not a single argv: the stage3 `Unpack` (download + `verify.verify_hashes`
  gate + `tar`), `mount.write_target_fstab_file`, the `make.conf` render/write, and
  every file-writing-seam config write.

Three concrete bodies, citing the real functions:

```python
# MountTarget — target-aware, no chroot. Runs on the host executor.
class MountTarget(FuncStep):
    label = "Mount the target"; phase = Phase.PREPARE_DISK
    chroot = False; target_aware = True
    async def run(self, ctx, on_progress):
        await mount.apply_mount_plan(ctx.plan.mount, ctx.host, on_progress=on_progress)
    async def is_satisfied(self, ctx):
        # the root device is already mounted at ctx.root
        return _is_mountpoint(ctx.root)

# EmergeWorld — chroot. The engine hands it ctx.target (a ChrootExecutor),
# so run_steps emits ["chroot", root, "emerge", "-uDN", ...] with no code change.
class EmergeWorld(ArgvStep):
    label = "Emerge @world"; phase = Phase.BASE_SYSTEM
    chroot = True; target_aware = False
    def build(self, ctx):
        argv = ["emerge", "-uDN", "--color", "n"]
        if ctx.plan.binary_pref:            # BINPREF: prefer binpkg, fall back to source
            argv.insert(1, "--getbinpkg")
        return steps.Step("emerge @world", [*argv, "@world"])
    async def is_satisfied(self, ctx):
        return ctx.state.done("emerge_world")   # no cheap probe; use the marker

# WriteFstab — target-aware, native (write under root, no chroot).
class WriteFstab(FuncStep):
    label = "Generate /etc/fstab"; phase = Phase.BASE_SYSTEM
    chroot = False; target_aware = True
    async def run(self, ctx, on_progress):
        text = mount.generate_target_fstab(ctx.plan.mount, ctx.uuids)
        path = mount.write_target_fstab_file(ctx.root, text)
        if on_progress: on_progress([f"wrote {path}"])
    async def is_satisfied(self, ctx):
        return os.path.exists(rootpath.resolve(ctx.root, "/etc/fstab"))
```

The pattern is uniform: a `chroot` step calls the executor and lets `ChrootExecutor`
add the `chroot <root>` prefix; a `target_aware` step resolves its path under `root`
via the seam (`rootpath.resolve`, `paths.make_conf(root)`, `mount.*_target_*`) and
writes on the host.

## 2. The `InstallContext`

A plain object threaded to every step's `run`/`is_satisfied`. It carries the
already-decided runtime and the approved plan; steps read it, they do not mutate the
plan.

| Field | Type | Source |
|---|---|---|
| `root` | `str` | the target root, `/mnt/gentoo` by convention (guarded by `mount.guard_target_root`) |
| `host` | `Executor` | `choose_executor()` → `DirectExecutor` on the live CD |
| `target` | `ChrootExecutor` | `ChrootExecutor(host, root)` — the in-target view of the same executor |
| `plan` | `InstallPlan` | the reviewed, approved plan (§7) |
| `uuids` | `dict[str, str]` | device→UUID map for `generate_target_fstab`, read after mkfs |
| `state` | `StateStore` | the completed-step marker store (§6) |

The engine picks the executor per step, so a step never touches `choose_executor`
itself:

```python
executor = ctx.target if step.chroot else ctx.host
```

`ctx.target` is constructed once, *after* the target root is mounted and stage3 is
unpacked — `ChrootExecutor.__init__` runs `mount.guard_target_root(root)`, which is
harmless before then, but there is nothing to chroot *into* until stage3 lands. All
`chroot=False` steps use `ctx.host`; every `chroot=True` step uses `ctx.target` and is
oblivious to the difference — that is the entire point of the `ChrootExecutor` seam.

The user's config selections live in `plan` (§7), not loose on the context: timezone,
locale, hostname, keymap, profile target, kernel method, bootloader firmware/target,
root-password handling, the optional user account, and the network choices. This keeps
the context a small runtime handle and the plan a single inspectable value.

## 3. The step registry — twenty `InstallStep`s

The registry is one ordered list, grouped by phase, built from the approved
`InstallPlan`. Its order is the contract a test asserts on (the `plan_steps`
ordering-assertion pattern lifted up a level). The chroot boundary is explicit: a
single `PrepareChroot` step (`prepare_chroot`) opens it before the first `chroot=True`
step, and `teardown_chroot` closes it in the engine's `finally` (§5), never as a step.

| # | Phase | `InstallStep` | Module call / argv | chroot | target_aware | `is_satisfied` |
|---|---|---|---|---|---|---|
| 1 | Prepare disk | `Partition` | `provision.apply_plan(plan.disk, host, devices, mounts, boot_source=…)` | no | no | marker (destructive; never auto-skip silently — see §6) |
| 2 | Prepare disk | `MakeFilesystems` | folded into `provision.plan_steps` (mkfs/mkswap/swapon) run by #1 | no | no | with #1 |
| 3 | Prepare disk | `MountTarget` | `mount.apply_mount_plan(plan.mount, host)` | no | yes | `ctx.root` is a mountpoint |
| 4 | Base system | `UnpackStage3` | download + `verify.verify_hashes` + `tar` (the `Stage3` `Unpack` flow) | no | yes | `<root>/etc/gentoo-release` present *and* marker set |
| 5 | Base system | `WriteFstab` | `mount.generate_target_fstab` + `mount.write_target_fstab_file(root, …)` | no | yes | `<root>/etc/fstab` exists |
| 6 | Base system | `WriteMakeConf` | render + write `paths.make_conf(root)` (+ mirrors/binhost drop-ins) | no | yes | `<root>/etc/portage/make.conf` exists |
| 7 | Base system | `PrepareChroot` | `prepare_chroot(root, host)` — pseudo-fs mounts + `resolv_copy_step` | no | yes | proc mounted under root |
| 8 | Base system | `SyncTree` | `emerge --sync --color n` | **yes** | no | marker (no cheap probe) |
| 9 | Base system | `SetProfile` | `eselect.set_argv("profile", n)` | **yes** | no | current profile == chosen |
| 10 | Base system | `EmergeWorld` | `emerge -uDN [--getbinpkg] --color n @world` | **yes** | no | marker |
| 11 | Configure | `SetTimezoneLocale` | system `SetTimezone`/`SetLocale` writers, `root=ctx.root` | no | yes | target file matches |
| 12 | Configure | `SetHostname` | system `SetHostname`, `root=ctx.root` | no | yes | `<root>/etc/conf.d/hostname` matches |
| 13 | Configure | `SetConsole` | `console.set_conf_value` keymap/font, `root=ctx.root` | no | yes | `<root>/etc/conf.d/keymaps` matches |
| 14 | Kernel & boot | `BuildKernel` | `kernel.build_steps(BuildConfig(...))` via the target executor | **yes** | no | marker (long; source_dir built) |
| 15 | Kernel & boot | `InstallBootloader` | `bootloader.install_steps(InstallConfig(firmware, boot_directory, …))` | **yes**¹ | yes¹ | marker |
| 16 | Users & network | `SetRootPassword` | `users.chpasswd_input("root", pw)` (stdin) | **yes** | no | always re-run if requested |
| 17 | Users & network | `CreateUser` | `users.useradd_argv(...)` + `users.gpasswd_argv("wheel", user, add=True)` | **yes** | no | user present in `<root>/etc/passwd` |
| 18 | Users & network | `ConfigureNetwork` | netifrc writer + `resolv`/`hosts` writers, `root=ctx.root` | no | yes | target files present |
| 19 | Finish | `Tier2Optional` | sshd/firewall/privilege/sysctl writers, `root=ctx.root` (opt-in, off by default) | no/yes | yes | per-module |
| 20 | Finish | *(teardown)* | `teardown_chroot(root, host)` — **not a step**; runs in `finally` (§5) | — | — | — |

¹ `grub-install` uses the `InstallConfig.boot_directory`/`efi_directory` seam and can
run on the host; `grub-mkconfig` probes the running kernel/mounts and must run in the
chroot. `InstallBootloader` therefore runs its two `install_steps` phases through
`ctx.target`, which is simplest and matches the Handbook; the `boot_directory` seam is
kept for the BIOS/host-side follow-on.

Steps 11–13 and 18–19 are the pure seam: they resolve their managed path under
`ctx.root` (`rootpath.resolve`, `paths.*(root)`) and write on the host, exactly as the
running-system maintenance path does with `root == "/"`. Because `rootpath.is_target`
is true for a target root, those writers already skip their live side-effects
(`env-update`, `sysctl -p`, service reloads) — no install-specific branch.

## 4. Progress streaming

The engine is UI-agnostic and exposes exactly the callback contract the partition,
kernel, mount-target, and `RunScreen` apply screens already consume, so the step-5 TUI
renders a per-phase table + bar and a live log with no adapter:

- **`on_step(index: int)`** — called as each `InstallStep` starts, with its index in
  the ordered registry. This is the same `on_step` signature `run_steps`,
  `apply_plan`, `apply_mount_plan`, `prepare_chroot`, and `build`/`install` all take.
  The TUI advances the current row and the progress bar.
- **`on_progress(lines: list[str])`** — the `OnProgress` type from
  `core/exec/runner.py`: each streamed line arrives as a one-element batch (or a
  coalesced batch from the backend's `Progress` signal), the same shape `stream`
  emits. The TUI appends to the raw log and parses markers to advance rows, exactly as
  `RunScreen._consume` does.

The engine's public entry point mirrors the module apply functions:

```python
async def run_install(
    ctx: InstallContext,
    steps: list[InstallStep],
    *,
    on_progress: OnProgress | None = None,
    on_step: Callable[[int], None] | None = None,
) -> None: ...
```

The TUI supplies a `run_op` closure to `RunScreen` that calls `run_install`; the phase
grouping (`InstallStep.phase`) drives the per-phase headers. Nothing in the engine
imports `urwid` or knows a screen exists — the callback contract *is* the boundary, and
this doc defines it so step 5 can be written against a stable surface.

## 5. Failure + teardown

- **Stop at the first failure.** `run_install` runs the steps in order; the first
  `StepError` (from `run_steps`), `DiskApplyError` (from `apply_plan`), or `ValueError`
  (a guard, a malformed plan) propagates out with a clear, labelled message — the
  `StepError`/`DiskApplyError` shape the TUI already renders. No later step runs. The
  raw log remains viewable, as everywhere else.
- **Teardown always runs.** The pseudo-filesystems are opened by `PrepareChroot`
  (step 7). The engine wraps the whole run so that once `prepare_chroot` has run,
  `teardown_chroot(root, host)` runs in a `finally` — on success, on a `StepError`, and
  on an abort. `teardown_chroot` is best-effort by construction (each lazy unmount runs
  independently and it never raises), so it cannot mask the original failure, and a
  partial install leaves a target whose real filesystems can be cleanly unmounted.

```python
async def run_install(ctx, steps, *, on_progress=None, on_step=None):
    opened_chroot = False
    try:
        for index, step in enumerate(steps):
            if await step.is_satisfied(ctx):
                if on_progress: on_progress([f"✓ {step.label} (already done)"])
                continue
            if on_step: on_step(index)
            executor = ctx.target if step.chroot else ctx.host
            await step.run(ctx, on_progress)         # raises on failure
            if isinstance(step, PrepareChroot): opened_chroot = True
            ctx.state.mark(step)                     # record completion (§6)
    finally:
        if opened_chroot:
            await teardown_chroot(ctx.root, ctx.host, on_progress=on_progress)
```

**What is and isn't rolled back.** Only mounts are undone — the pseudo-filesystems by
`teardown_chroot`, and the target's own filesystems by the caller's normal
unmount-target flow. Writes are **not** rolled back: a written `make.conf`, an unpacked
stage3, or a partially-merged `@world` stays on disk. That is deliberate — it is
exactly what makes resume (§6) possible, and undoing a stage3 unpack or an emerge is
not a meaningful operation. A failed run leaves an inspectable, cleanly-unmountable
target that a re-run can continue.

## 6. Resume / idempotency

A re-run of the same `InstallPlan` skips every step whose `is_satisfied(ctx)` is true,
then continues from the first unsatisfied one. Two kinds of step:

- **Naturally idempotent** (no marker needed): the seam writes (fstab, make.conf,
  timezone/locale/hostname/keymap, network) — re-writing the same file is a no-op, and
  `is_satisfied` is a cheap file/content check. `MountTarget` re-checks the mountpoint.
  `SetProfile` checks the current profile symlink. `CreateUser` greps `<root>/etc/passwd`.
- **Marker-gated** (expensive, no cheap probe, or destructive): `UnpackStage3`,
  `SyncTree`, `EmergeWorld`, `BuildKernel`, `InstallBootloader`, and `Partition`.
  `UnpackStage3` also checks a real signal (`<root>/etc/gentoo-release`) so a fresh
  target is never assumed done; the marker guards against re-unpacking over a target
  the user has already started building.

**Where the marker persists (resolving `installer.md` open question 6).** Two-phase,
because the natural home does not exist yet at the start:

1. **Before stage3**, there is no target filesystem to write into, so the marker lives
   in a **live-session file under `/run`** (e.g. `/run/gest/install-state.json`), which
   the live CD provides and which is discarded on reboot — correct, because nothing
   before stage3 has produced anything a reboot could resume *into*.
2. **After stage3 is unpacked**, the marker moves to the **target's own state dir**,
   `paths.gest_state("install-state.json", ctx.root)` → `<root>/etc/portage/gest/…`
   (the GeST-private location `paths.gest_dir(root)` already defines, which Portage and
   `eselect` never read). This survives a reboot, so an install interrupted after
   stage3 can be resumed after rebooting back into the live CD and re-mounting the
   target.

The `StateStore` reads `/run` first and, once `<root>/etc/portage/gest/` exists,
prefers and writes there. This is the minimum that makes "don't re-unpack stage3, don't
re-emerge `@world`" work across both an in-session retry and a reboot, and it reuses the
state-dir convention already in `core/portage/paths.py` rather than inventing a
location.

## 7. The plan-review contract

The whole run is assembled and reviewed **before** a single step executes — the
`DiskPlan` discipline lifted to the install. `InstallPlan` is a plain, frozen value
type (like `DiskPlan`/`MountPlan`), so it is inspectable, testable, and renderable
without running anything:

```python
@dataclass(slots=True, frozen=True)
class InstallPlan:
    disk: DiskPlan                 # provision.uefi_plan(...) — the destructive layout
    mount: MountPlan               # mount.derive_mount_plan(disk, root)
    stage3: Stage3Selection        # resolved URL/filename/size/digests_url/signature_url
    profile: int                   # eselect profile target number
    kernel: BuildConfig            # method ("make"|"genkernel"), jobs, initramfs
    bootloader: InstallConfig      # firmware ("uefi"|"bios"), efi_directory, boot_directory
    hostname: str
    timezone: str
    locale: str
    keymap: str
    root_password: bool            # whether to set it (the secret is prompted at run, never stored in the plan)
    user: UserSpec | None          # name, comment, shell, wheel
    network: NetworkSpec           # netifrc/resolv/hosts choices
    binary_pref: bool              # @world source vs. --getbinpkg (see open questions)
    tier2: frozenset[str]          # opt-in day-2 modules, empty by default
```

The engine builds the ordered registry (§3) from an `InstallPlan` and executes **only**
an approved one. The step-5 TUI renders the plan for review as a unit and takes the
partitioner's **typed-device-name confirmation** for the destructive disk phase
(reusing `provision.validate_plan` / `guard_provision_target` and the current-vs-planned
diff) before `run_install` is ever called. Secrets are the one thing not in the value:
`root_password` is a boolean, and the actual password is supplied to `SetRootPassword`
at run time (fed to `chpasswd_input` on stdin, never in argv, never persisted), so an
`InstallPlan` is safe to log, diff, and snapshot in a test.

## 8. Where it runs / privilege

The installer runs on a Gentoo minimal CD as root, so `choose_executor()` returns
`DirectExecutor` (its `geteuid() == 0` branch) — the same path the partitioner, kernel,
and mount-target screens already take. `ChrootExecutor` requires uid 0 (that is its
whole precondition, and the `DirectExecutor` precondition), so the chroot mechanism
composes cleanly with the already-root model and needs no D-Bus surface. `ChrootExecutor`
guards its root with `mount.guard_target_root` at construction, so it can never wrap
`/`. `DBusExecutor` is a stub that raises; the installer is therefore **not offered on
the unprivileged installed-system path** — an installed system is administered, not
re-installed, and the flow engine is simply not reachable there.

## 9. Sequencing within step 4

Each sub-step is independently landable and testable, and each unblocks the next — the
same argument that made "modules first" correct.

1. **The types + a trivial pipeline.** `InstallStep`/`InstallContext`/`InstallPlan`,
   `ArgvStep`/`FuncStep`, and `run_install`, plus a `FakeExecutor`-driven test that a
   toy three-step flow runs in order, picks host-vs-chroot correctly, and tears down.
   No module calls yet — pure engine mechanics.
2. **The step registry.** Wire the twenty entries to the real module functions
   (`apply_plan`, `apply_mount_plan`, `write_target_fstab_file`, `prepare_chroot`,
   stage3 unpack, `set_argv`, `emerge …`, `build_steps`, `install_steps`,
   `chpasswd_input`, the seam writers). Assert Handbook order and the chroot boundary
   over a `FakeExecutor`.
3. **The minimal bootable end-to-end.** The smallest set that boots:
   `Partition → MountTarget → UnpackStage3 → WriteFstab → WriteMakeConf →
   PrepareChroot → SyncTree → SetProfile → EmergeWorld → BuildKernel →
   InstallBootloader → SetRootPassword → teardown`. Verified on a scratch disk from a
   live CD (the partitioner's manual test path).
4. **Resume.** The `StateStore` (§6), `is_satisfied` on the marker-gated steps, and the
   `/run`→target-state-dir move. Tested by running the flow twice against a
   `FakeExecutor` and asserting the second run skips the completed steps.

**Why this ordering is right.** Sub-step 1 is pure mechanics with no module coupling,
so the model can be nailed down and unit-tested before any real command is wired.
Sub-step 2 is where the registry becomes the single ordering contract — the one thing a
test must pin. Sub-step 3 is a *subset* of the registry (config phases 11–13 and the
optional Tier-2 phase 19 dropped), so it is a filter over an already-tested list, not
new code, and it is the first thing that produces a booting system — the milestone.
Resume (4) is a pure addition on a working core: it changes when steps run, never what
they do.

## 10. Testing

None of these wipe a disk; all follow the established `plan_steps`/`apply_plan`
patterns.

- **Ordered-argv capture.** A `FakeExecutor` records the entire ordered argv the whole
  flow would run, *including* the `["chroot", root, …]` prefixes `ChrootExecutor` adds.
  A test asserts (a) Handbook order across phases, (b) that every `chroot=True` step's
  recorded argv begins with `chroot <root>` and every `chroot=False` step's does not,
  and (c) that `prepare_chroot`'s mounts appear before the first chroot argv and
  `teardown_chroot`'s unmounts after the last — the chroot boundary made a test
  assertion. This is the same double the partitioner's `apply_plan` and
  `apply_mount_plan` pipelines already use.
- **Resume / idempotency.** Run the flow twice against one `FakeExecutor`; assert the
  second run's recorded argv omits the marker-gated steps and the satisfied seam writes,
  and that `is_satisfied` was consulted for each. Test the `/run`→target-state-dir move
  by pointing `paths.gest_state` at a temp root.
- **`InstallPlan` assembly/validation is pure.** Build a plan from `uefi_plan` +
  `derive_mount_plan` + a resolved `Stage3Selection` and assert the derived registry and
  its order — no execution, like `plan_steps` ordering tests. Malformed plans (bad
  profile number via `eselect.set_argv`, missing UUID via `generate_target_fstab`) raise
  before any step runs.
- **Teardown-on-failure.** A `FakeExecutor` whose `code_for` fails at `EmergeWorld`;
  assert `teardown_chroot`'s unmounts still appear in the recorded argv (the `finally`
  path) and that no later step ran.
- **Live-CD manual test.** The real test, inherited from the partitioner: boot a
  minimal CD (`DirectExecutor` auto-selected), install onto a scratch disk, reboot into
  it.

## 11. Non-goals (engine-specific)

- **The installer TUI** — step 5. This doc defines the `on_step`/`on_progress` callback
  contract (§4) and the `InstallPlan` review value (§7) it consumes, not the screens.
  How selections are *gathered* (a wizard vs. a single form) is entirely the TUI's
  concern.
- **Unattended / declarative install** — the first installer is interactive and
  reviewed; a plan-from-file is a later possibility that would reuse `InstallPlan`
  unchanged.
- **No-wipe (existing-partition) install** — needs its own safety review (§12); the
  engine assumes Phase 1 provisions.
- **LUKS / LVM / RAID** — still deferred at the storage layer, so the engine targets the
  plain GPT/UEFI layout `uefi_plan` builds; they layer on the same steps later.
- **Rollback of writes** — only mounts are torn down (§5).
- **systemd** — OpenRC only; stage3 offers only the OpenRC `VARIANTS`.

## 12. Open questions — resolved

Each parent-doc open question, answered concretely:

1. **Stage3 variant.** Default to `stage3-*-openrc` (`model.DEFAULT_VARIANT`), offer the
   other OpenRC `VARIANTS` (desktop, hardened, no-multilib). *Because* it is the
   Handbook default and the smallest bootable base; the model already encodes exactly
   this set and excludes systemd.
2. **Profile timing.** Run `SetProfile` (`eselect.set_argv("profile", n)`) in the chroot
   **before** `EmergeWorld`. *Because* the profile sets the USE defaults the `@world`
   build compiles against; setting it afterward would mean an immediate rebuild.
3. **Binary vs. source `@world`.** Offer **binary-preferred with source fallback** —
   `InstallPlan.binary_pref` toggles `--getbinpkg` on the `emerge -uDN @world` argv,
   matching the module's existing `BINPREF` mode (`core/software/selection.py`).
   *Because* it dramatically shortens the base merge while still building anything the
   binhost lacks; plain source is the toggle-off case.
4. **How much Tier 2 during install.** Opt-in, **off by default** — `InstallPlan.tier2`
   is an empty set unless the user adds sshd/firewall/sudo-doas/sysctl/Wi-Fi (phase 19).
   *Because* the milestone is a bootable base; day-2 config is safely a first-boot task
   and folding it in is a pure addition.
5. **No-wipe path.** **Not in step 4.** Recommend a follow-on that supplies a
   pre-built `MountPlan` and skips steps 1–2 while still writing fstab from the chosen
   devices. *Because* "don't wipe, but do mkfs/mount what I picked" needs its own safety
   review distinct from the partitioner's whole-disk guards.
6. **Resume-marker location.** Session file under `/run` before stage3, then
   `paths.gest_state(name, root)` under `<root>/etc/portage/gest/` after (§6). *Because*
   the durable home does not exist until stage3 unpacks, and nothing before stage3
   produces resumable state anyway.
7. **Pseudo-fs teardown ownership.** The **engine's `finally`**, calling the
   best-effort, never-raising `teardown_chroot` — never an individual step (§5).
   *Because* only the engine spans the whole run and can guarantee unmount on any exit
   path; a step cannot unmount after its own failure.

New questions the engine surfaces:

- **Profile-set vs. first `@world` interaction** — resolved as (2): profile first.
  Confirmed by putting `SetProfile` (#9) before `EmergeWorld` (#10) in the registry.
- **A binpkg cache bind-mount** — should the engine bind a host binpkg/distfiles cache
  into the target to speed `--getbinpkg` and avoid re-downloading? Deferred: the
  pseudo-fs set (`pseudo_mount_steps`) is fixed to proc/sys/dev/run today, and adding an
  optional cache bind is a small, separable follow-on with its own teardown entry.
- **How selections are gathered before review** — a wizard vs. a single form. Noted as
  the **step-5 TUI's concern**; the engine only requires a fully-populated,
  already-reviewed `InstallPlan`.
