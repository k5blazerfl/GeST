# A GeST installer live image

GeST's north star is to facilitate a full Gentoo install. The natural delivery is
a **bootable live image that boots straight into GeST's installer** — a Gentoo
minimal environment plus `app-admin/gest` and the tools its install path drives,
with the image autologging in and launching `gest` on the console.

Two targets boot very differently:

| Target | Medium | Boots how | Status |
|---|---|---|---|
| **amd64** | hybrid ISO (USB/CD/VM) | firmware boots the ISO directly (BIOS **and** UEFI) | **buildable here** |
| **arm64 / Apple Silicon (M1/M2)** | UEFI live USB (arm64 `BOOTAA64.EFI`) | **not** direct — via an already-installed m1n1+U-Boot chain | documented, follow-on |

## Contents

```
config.env                    # host/time-specific values you fill (snapshot, stage3 seed, overlay)
build.sh                      # render the specs from config.env + build with catalyst
qemu-test.sh                  # boot a built ISO in QEMU (BIOS or UEFI) with a scratch disk
amd64/livecd-stage1.spec.in   # catalyst templates (${VARS} filled by build.sh)
amd64/livecd-stage2.spec.in
amd64/gest.packages           # the image's package set (gest + install-path tools)
amd64/fsscript.sh             # runs in the stage2 chroot: autologin root + launch gest
amd64/motd                    # the console message
portage-conf/                 # ~amd64 keyword for the gest ebuild
```

## Quick start — one command

On a Gentoo host with catalyst + qemu installed, from an up-to-date checkout:

```sh
sudo emerge -av dev-util/catalyst app-emulation/qemu sys-firmware/edk2-ovmf
sudo packaging/livecd/spin-up.sh            # add --uefi to boot via OVMF
```

`spin-up.sh` does everything: syncs this checkout's overlay into
`/var/db/repos/gest` (so the image carries the **latest GeST**), ensures a portage
snapshot, downloads the latest `stage3-amd64-openrc` seed, writes `config.env`,
builds the ISO, and boots it in QEMU. `--no-boot` builds only;
`--snapshot <id>` overrides the snapshot (catalyst's snapshot naming varies by
version — pass this if the auto value fails). The manual flow below is what it
wraps.

## amd64 — build a live ISO with catalyst

The standard Gentoo two-livecd-stage flow on a stage3, wrapped so you don't
hand-edit spec files. `build.sh` renders `amd64/*.spec.in` (substituting
`config.env`, appending `gest.packages`) into `build/` and runs catalyst on them.

### Prerequisites (on a Gentoo build host)

```sh
sudo emerge -av dev-util/catalyst app-emulation/qemu sys-firmware/edk2-ovmf
# configure catalyst: /etc/catalyst/catalyst.conf (storedir, distdir, …)
# stage a portage snapshot and a stage3 seed under catalyst's builds/:
sudo catalyst -s stable            # a snapshot id, e.g. 2026-08-13
# (download a stage3-amd64-openrc tarball into <storedir>/builds/default/)

# make app-admin/gest resolvable during the build — clone this repo's overlay:
sudo git clone https://github.com/k5blazerfl/GeST /tmp/gest \
  && sudo cp -a /tmp/gest/packaging/overlay /var/db/repos/gest
```

### Configure + build

```sh
# 1. fill config.env: SNAPSHOT, STAGE3 (the seed subpath), GEST_OVERLAY
$EDITOR packaging/livecd/config.env

# 2. sanity-check the rendered specs without building:
RENDER_ONLY=1 packaging/livecd/build.sh amd64
cat packaging/livecd/build/livecd-stage1.spec      # inspect

# 3. build (hours from source; gentoo-kernel-bin + a binpkg seed cut it a lot):
sudo packaging/livecd/build.sh amd64
# → <catalyst storedir>/builds/…/gest-installer-amd64-<stamp>.iso
```

`build.sh` refuses to run while `config.env` still holds the `CHANGE-ME`
placeholders. The rendered `build/` specs are throwaway output (git-ignored).

### The image on boot

`fsscript.sh` (catalyst's `livecd/fsscript`) sets the image up to **autologin
root on tty1 and launch `gest`** — the gated **Install Gentoo** menu category
(shown because the live env is root) is the entry point. Exiting GeST drops to a
root shell. D-Bus and dhcpcd are enabled so the polkit-gated backend activates and
wired networking comes up for the stage3 download / emerges.

### Test in QEMU before real hardware

```sh
iso=<storedir>/builds/…/gest-installer-amd64-<stamp>.iso
packaging/livecd/qemu-test.sh "$iso" bios     # SeaBIOS
packaging/livecd/qemu-test.sh "$iso" uefi     # OVMF (edk2-ovmf)
```

Each boots the ISO with a fresh 20 GB scratch qcow2 disk, so you can run the
installer end to end (partition → stage3 → install → reboot) against a throwaway
target. Verify **both** BIOS and UEFI — GeST's bootloader step installs GRUB for
whichever firmware the plan selects.

## arm64 / Apple Silicon — why it's not an ISO

Apple Silicon Macs **cannot boot external media directly**: the firmware only
boots signed objects from internal storage. The Asahi boot chain solves this in
two steps, and only the second can touch a USB stick:

1. **One-time, from macOS:** the Asahi installer provisions **m1n1 → U-Boot →
   GRUB** into an internal EFI system partition (on Gentoo, automated by
   `chadmed`'s `asahi-gentoosupport` / `asahi-scripts`, which also install the
   Asahi kernel, device trees and GPU firmware from the **Asahi overlay**).
2. **After that,** U-Boot's UEFI can run an arm64 UEFI binary off a USB drive
   (`/EFI/BOOT/BOOTAA64.EFI`) — so a GeST **arm64 live USB** is bootable, but only
   once the internal m1n1+U-Boot chain exists.

So the M2 deliverable is an **arm64 UEFI live-USB image**, not an ISO, and it
presumes the machine already carries the Asahi boot stub. Practically, for testing
GeST on an M2, easiest first:

- **Run GeST inside an installed/minimal Asahi Gentoo** (`emerge app-admin/gest`).
  Exercises every module on real Apple-Silicon hardware today, with none of the
  live-image plumbing. Recommended first.
- **Build an arm64 UEFI live image** — a follow-on that reuses this amd64 harness
  with `subarch: arm64`, an arm64 profile, and the Asahi overlay + kernel/m1n1/
  U-Boot added to the package set, packed as a UEFI USB image rather than an
  isohybrid CD, booted via the already-installed U-Boot.

Caveats: Gentoo Asahi targets M1/M2 (M3+ unsupported), and some monthly Asahi
images have had M2 boot regressions — pin a known-good Asahi base when testing.

## Sequencing

1. **amd64 ISO** — build with this harness, verify in QEMU (BIOS + UEFI), then on
   real hardware. Fast feedback loop; proves "boots into GeST installer" end to end.
2. **GeST on installed Asahi Gentoo** (M2) — no image work; validates every module
   on Apple Silicon.
3. **arm64 UEFI live-USB** — the true M2 live installer, reusing this harness with
   the Asahi overlay + arm64 profile.

## Sources

- [Catalyst / Custom Media Image (Gentoo Wiki)](https://wiki.gentoo.org/wiki/Catalyst/Custom_Media_Image)
- [livecd-stage2 spec template (catalyst)](https://gitweb.gentoo.org/proj/catalyst.git/plain/examples/livecd-stage2_template.spec)
- [Project:Asahi (Gentoo Wiki)](https://wiki.gentoo.org/wiki/Project:Asahi)
- [Installing Gentoo with LiveCD (Asahi wiki)](https://leo3418.github.io/asahi-wiki-build/installing-gentoo-with-livecd/)
- [Asahi overlay (chadmed)](https://github.com/chadmed/asahi-overlay)
- [U-Boot for Apple Silicon (boots UEFI off USB once installed)](https://docs.u-boot.org/en/latest/board/apple/m1.html)
