# A GeST installer live image

GeST's north star is to facilitate a full Gentoo install. The natural delivery is
a **bootable live image that boots straight into GeST's installer** — a Gentoo
minimal environment plus `app-admin/gest` and the tools its install path drives.

There are two very different targets, because the two architectures boot
differently:

| Target | Medium | Boots how | Status |
|---|---|---|---|
| **amd64** | hybrid ISO (USB/CD/VM) | firmware boots the ISO directly (BIOS **and** UEFI) | scaffolded here |
| **arm64 / Apple Silicon (M1/M2)** | UEFI live USB (arm64 `BOOTAA64.EFI`) | **not** direct — via an already-installed m1n1+U-Boot chain | documented, not scaffolded |

## amd64 — a normal Gentoo live ISO (catalyst)

Built with **catalyst**, Gentoo's release tool, in the standard two-livecd-stage
flow on top of a stage3:

1. `livecd-stage1` — a stage3 source + a package list (`amd64/gest.packages`):
   installs `app-admin/gest` and the install-path tools into the build root.
2. `livecd-stage2` — adds the kernel + bootloader and packs the squashfs into a
   hybrid ISO that boots BIOS and UEFI.

The GeST overlay is threaded in via `portage_overlay` so `app-admin/gest` resolves
(the same overlay `packaging/overlay/` and Amphitheater already publish). See
`amd64/livecd-stage1.spec` and `amd64/livecd-stage2.spec`; `build.sh` runs both.

The result — `gest-installer-amd64-<stamp>.iso` — boots on any PC or VM
(test it in QEMU with `qemu-system-x86_64 -m 4G -cdrom …` for both `-bios` and
OVMF/UEFI) and drops the user at a root console that auto-launches `gest`; the
gated **Install Gentoo** menu category (shown because the live env runs as root)
is the entry point.

### Build (on a Gentoo host with `dev-util/catalyst`)

```sh
# 1. a recent portage snapshot + a stage3 seed (catalyst fetches these)
# 2. register the GeST overlay where the spec's portage_overlay points
#    (e.g. clone this repo's packaging/overlay to /var/db/repos/gest)
# 3. build:
sudo packaging/livecd/build.sh amd64
# → /var/tmp/catalyst/builds/…/gest-installer-amd64-<stamp>.iso
```

Catalyst builds are finicky and slow (a full source build takes hours); the specs
here are a working starting point to iterate on, not a turnkey CI artifact. A
binary-package (`--getbinpkg`) seed and a `gentoo-kernel-bin` kernel cut the time
dramatically — see the notes in the stage2 spec.

## arm64 / Apple Silicon — why it's not an ISO

Apple Silicon Macs **cannot boot external media directly**: the firmware only
boots signed objects from internal storage. The Asahi project's boot chain solves
this in two steps, and only the second can touch a USB stick:

1. **One-time, from macOS:** the Asahi installer provisions **m1n1 → U-Boot →
   GRUB** into an internal EFI system partition (this is what "installing Asahi"
   sets up; on Gentoo it's automated by `chadmed`'s `asahi-gentoosupport` /
   `asahi-scripts`, which also install the Asahi kernel, device trees and GPU
   firmware from the **Asahi overlay**).
2. **After that,** U-Boot's UEFI implementation *can* run an arm64 UEFI binary
   off a USB drive (`/EFI/BOOT/BOOTAA64.EFI`) — so a GeST **arm64 live USB** is
   bootable, but only once the internal m1n1+U-Boot chain exists.

So the M2 deliverable is **not** a CD/ISO but an **arm64 UEFI live-USB image**,
and it depends on the machine already carrying the Asahi boot stub. Practically,
for testing GeST on your M2 there are two paths, easiest first:

- **Run GeST inside an installed/minimal Asahi Gentoo** (overlay added, `emerge
  app-admin/gest`). This exercises every GeST module on real Apple-Silicon
  hardware today, with none of the live-image plumbing. Recommended first.
- **Build an arm64 UEFI live image** (catalyst `subarch: arm64`, the Asahi
  overlay + kernel/m1n1/U-Boot in the package list, packed as a UEFI live USB
  rather than an isohybrid CD), booted via the already-installed U-Boot. This is
  the real "GeST live USB for M2" and is a follow-on once the amd64 image is
  proven — it reuses the same package set with the Asahi overlay and an arm64
  profile.

Caveats worth noting: the Gentoo Asahi images target M1/M2 (ARM64); M3+ are not
yet supported, and specific monthly Asahi images have had M2 boot regressions — so
pin a known-good Asahi base when testing.

## Sequencing

1. **amd64 ISO** — scaffolded here; iterate the specs to a booting image, verify
   in QEMU (BIOS + UEFI), then on real hardware. This is the fast feedback loop
   and proves the "boots into GeST installer" concept end to end.
2. **GeST on installed Asahi Gentoo** (M2) — no image work; validates every module
   on Apple Silicon.
3. **arm64 UEFI live-USB** — the true M2 live installer, reusing the amd64 package
   set with the Asahi overlay + arm64 profile, packed as a UEFI USB image.

## Sources

- [Catalyst / Custom Media Image (Gentoo Wiki)](https://wiki.gentoo.org/wiki/Catalyst/Custom_Media_Image)
- [livecd-stage2 spec template (catalyst)](https://gitweb.gentoo.org/proj/catalyst.git/plain/examples/livecd-stage2_template.spec)
- [Project:Asahi (Gentoo Wiki)](https://wiki.gentoo.org/wiki/Project:Asahi)
- [Installing Gentoo with LiveCD (Asahi wiki)](https://leo3418.github.io/asahi-wiki-build/installing-gentoo-with-livecd/)
- [Asahi overlay (chadmed)](https://github.com/chadmed/asahi-overlay)
- [U-Boot for Apple Silicon (boots UEFI off USB once installed)](https://docs.u-boot.org/en/latest/board/apple/m1.html)
