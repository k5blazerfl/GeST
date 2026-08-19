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
packaging/livecd/run-on-builder.sh --boot        # build remotely, pull ISO, boot it locally
packaging/livecd/run-on-builder.sh --boot --uefi # same, OVMF instead of SeaBIOS
```

It rsyncs your current checkout (latest HEAD, no push needed), runs
`spin-up.sh --no-boot` on the builder, and pulls the ISO (+ `.sha256`) into
`~/gest-isos`. Boot-testing stays **local on purpose** — `qemu-test.sh` opens a
QEMU display a headless builder can't show.

Useful flags: `--out DIR` (where the ISO lands), `--snapshot ID` /
`--storedir DIR` (passthrough to catalyst), `--sync-only` (just push the
checkout).

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
- An automated pass/fail boot smoke (`qemu-test.sh` is currently interactive)
  and a build-log version-assertion gate — next on the maintenance roadmap.
