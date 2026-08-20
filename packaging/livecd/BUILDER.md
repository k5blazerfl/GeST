# Offloading ISO builds to a dedicated Gentoo builder

Catalyst is CPU/IO-heavy and shouldn't run on your laptop. This offloads the
build to a spare Gentoo box, then pulls the finished ISO back for local
boot-testing. The builder is a plain Gentoo box you install yourself — **no GeSI
dependency**, which sidesteps the chicken-and-egg of needing the installer to
stand up the machine that builds the installer.

## One-time: stand up the builder

1. **You:** install Gentoo on the spare box — an **amd64 systemd desktop**
   profile (`default/linux/amd64/23.0/desktop/systemd`), matching the ISO target
   so binpkgs are reusable. A stage3 + handbook install is enough; give it a
   fast disk and plenty of cores/RAM (catalyst is heavy). Enable SSH.

2. **Push this checkout over and provision it** (idempotent — safe to re-run):

   ```sh
   # from your dev box: get the repo onto the builder
   packaging/livecd/run-on-builder.sh --builder you@builder --sync-only
   # then, on the builder:
   sudo ~/gest-build/packaging/livecd/provision-builder.sh --serve
   ```

   `provision-builder.sh` installs catalyst + qemu, registers the GeST and
   Amphitheater overlays, mirrors this repo's `portage-conf/` into
   `/etc/portage` (so the builder's binpkgs match the ISO), turns on
   `FEATURES=buildpkg`, and — with `--serve` — exposes `/var/cache/binpkgs` as a
   Portage binhost over HTTP. It also verifies the box is a systemd/amd64
   desktop profile and warns if not.

3. **Point the driver at it** by adding a `BUILDER=` line to
   `packaging/livecd/config.env` (or pass `--builder` / set `$BUILDER` each run):

   ```sh
   BUILDER="you@builder"
   ```

## Each build

From the dev box:

```sh
packaging/livecd/run-on-builder.sh --smoke       # build remotely, pull ISO, headless PASS/FAIL
packaging/livecd/run-on-builder.sh --boot        # ... or open an interactive QEMU window instead
packaging/livecd/run-on-builder.sh --smoke --uefi # same, OVMF instead of SeaBIOS
```

It rsyncs your current checkout (latest HEAD, no push needed), runs
`spin-up.sh --no-boot` on the builder, and pulls the ISO (+ `.sha256`) into
`~/gest-isos`. QEMU runs **locally on purpose** — the headless builder has no
display. `--smoke` is the unattended gate (`boot-smoke.sh`: boots headless and
asserts the image reaches the greeter); `--boot` is the interactive window
(`qemu-test.sh`) for clicking through the installer.

Useful flags: `--out DIR` (where the ISO lands), `--snapshot ID` /
`--storedir DIR` (passthrough to catalyst), `--sync-only` (just push the
checkout).

## The validated build → release flow

The build is gated end to end — no manual "did it install the right version /
does it boot" checks:

1. **`run-on-builder.sh --smoke`** — builds on the builder, where `build.sh`
   automatically runs **`assert-iso-versions.sh`** after catalyst: the build
   *fails* if `app-admin/gest` / `gui-apps/hede` came from a stale **binary
   package** (the hede-0.3.0 fallback bug) or at a version that doesn't match the
   overlay. Then the ISO is pulled back and **`boot-smoke.sh`** boots it headless
   and asserts it reaches the greeter. Green here = the ISO installs the right
   versions *and* boots.
2. **`packaging/stack-status.py --strict --amphitheater /var/db/repos/amphitheater`**
   — before you tidelock, confirm every version line agrees across source ↔
   overlay ↔ Manifest ↔ Amphitheater ↔ the ISO you just built (`--build-log`).
3. Tidelock.

## The binhost dividend

With `--serve`, every build fills `/var/cache/binpkgs` and the box serves them.
Point the ISO build and installed systems at it to skip recompiles:

```sh
PORTAGE_BINHOST="http://<builder-ip>:8080"
```

This is the "B2 binhost" from the maintenance plan — it retires the
quickpkg-the-live-env hack and makes both ISO builds and GeSI installs fast.

## What's not automated (yet)

- The base OS install on the builder (step 1) — that's yours.
- Nightly/CI scheduling of `run-on-builder.sh --smoke` on the build host (the
  gate exists; wiring it to a timer/cron is the remaining step).
