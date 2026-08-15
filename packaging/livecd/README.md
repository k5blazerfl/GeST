# A GeST installer live image

GeST's north star is to facilitate a full Gentoo install. The natural delivery is
a **bootable live image that boots straight into a desktop** — a Gentoo
environment plus `app-admin/gest` and the tools its install path drives. The
amd64 image comes up in **HeDE** (the Helm Desktop Environment), whose Control
Center *is* GeST's Qt frontend; the user installs Gentoo from GeST (its TUI or
the graphical Control Center, both present). The arm64 image is still a
console-only `gest` installer (see the Apple-Silicon gap below).

Two targets boot very differently:

| Target | Medium | Boots how | Status |
|---|---|---|---|
| **amd64** | hybrid ISO (USB/CD/VM) | firmware boots the ISO directly (BIOS **and** UEFI) | **buildable here** |
| **arm64 / Apple Silicon (M1/M2)** | UEFI live USB (arm64 `BOOTAA64.EFI`) | **not** direct — via an already-installed m1n1+U-Boot chain | documented, follow-on |

## Contents

```
config.env                    # host/time-specific values you fill (snapshot, stage3 seed, overlays)
build.sh                      # render the specs from config.env + build with catalyst (arch arg)
spin-up.sh                    # amd64 turnkey: overlay + snapshot + stage3 + build + QEMU boot
qemu-test.sh                  # boot a built ISO in QEMU (BIOS or UEFI) with a scratch disk
run-on-asahi.sh               # install + run GeST inside an installed Asahi Gentoo (M1/M2)
amd64/…                       # amd64 spec templates, gest.packages, fsscript, motd
arm64/…                       # arm64 (Apple Silicon / Asahi) equivalents — scaffold
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
sudo emerge -av dev-util/catalyst app-emulation/qemu sys-firmware/edk2-bin

# IMPORTANT: catalyst packs the ISO with grub-mkrescue ON THE HOST, so the host's
# grub decides the ISO's boot images. A UEFI-only host grub → a UEFI-only ISO
# that BIOS machines can't boot. Ensure the BIOS (pc) platform is built:
sudo GRUB_PLATFORMS="pc efi-64" emerge -1 sys-boot/grub   # /usr/lib/grub/i386-pc must exist
# (build.sh warns if it's missing.)

# configure catalyst: /etc/catalyst/catalyst.conf (storedir, distdir, …)
# stage a portage snapshot and a stage3 seed under catalyst's builds/:
sudo catalyst -s stable            # snapshot treeish; sets SNAPSHOT=stable
# (download a stage3-amd64-openrc tarball into <storedir>/builds/default/)

# Overlays the build needs, cloned where config.env points (GEST_OVERLAY,
# HEDE_OVERLAY): app-admin/gest lives in this repo's overlay; gui-apps/hede lives
# in Amphitheater.
sudo git clone https://github.com/k5blazerfl/GeST /tmp/gest \
  && sudo cp -a /tmp/gest/packaging/overlay /var/db/repos/gest
sudo git clone https://github.com/k5blazerfl/Amphitheater /var/db/repos/amphitheater
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

**amd64** boots into **HeDE**. `gest.packages` pulls `gui-apps/hede` (which drags
in labwc, foot, gest, the polkit agent, wireplumber, …) plus `elogind`, `seatd`
and `greetd`; `app-admin/gest` is built with `USE=qt` (see
`portage-conf/package.use`) so the graphical Control Center is present. The root
overlay lays down `/etc/greetd/config.toml`, which **autologins the boot into the
HeDE session** (`dbus-run-session helm-session`) on vt1, and `fsscript.sh`
enables the `elogind` / `seatd` / `dbus` / `greetd` / `dhcpcd` services and frees
tty1 from the default getty. Inside HeDE the user runs GeST — TUI or Control
Center — to install; tty2-6 stay as rescue shells with `gest` on `PATH`.

**arm64** has no desktop: `fsscript.sh` there still autologins root on tty1 and
launches `gest` on the console.

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

## arm64 / Apple Silicon (Asahi)

This target is **scaffolded** (`arm64/` specs + `run-on-asahi.sh`), not a validated
build like amd64 — Apple Silicon boots very differently and catalyst's arm64 livecd
path is far less trodden. Read this section before building.

### Why it's not an ISO

Apple Silicon Macs **cannot boot external media directly**: the firmware only boots
signed objects from internal storage. The Asahi boot chain solves this in two
steps, and only the second can touch a USB stick:

1. **One-time, from macOS:** the Asahi installer provisions **m1n1 → U-Boot →
   GRUB** into an internal EFI system partition (on Gentoo, automated by `chadmed`'s
   `asahi-gentoosupport` / `asahi-scripts`, which also install the Asahi kernel,
   device trees and GPU firmware from the **Asahi overlay**).
2. **After that,** U-Boot's UEFI can run an arm64 UEFI binary off a USB drive
   (`/EFI/BOOT/BOOTAA64.EFI`) — so a GeST **arm64 live USB** is bootable, but only
   once the internal m1n1+U-Boot chain exists.

So the M2 deliverable is an **arm64 UEFI live-USB image**, not an ISO, and it
presumes the machine already carries the Asahi boot stub.

### Recommended first: run GeST *on* an installed Asahi Gentoo

The fastest way to exercise GeST on real M1/M2 hardware — no image build:

```sh
# on the Mac, from a GeST checkout, inside an installed Asahi Gentoo:
sudo packaging/livecd/run-on-asahi.sh --run
```

It registers this checkout as the GeST overlay, accepts `~arm64`, emerges
`app-admin/gest`, and launches it. This validates every GeST module on Apple
Silicon today.

### The arm64 live-USB build (scaffold)

Reuses the same harness with `subarch: arm64`, both overlays (GeST + Asahi), the
Asahi packages (`sys-apps/asahi-meta`, `virtual/dist-kernel:asahi`,
`sys-apps/asahi-scripts`, `sys-kernel/linux-firmware`), and an Asahi profile:

```sh
# register the Asahi overlay (chadmed's), then set config.env for arm64:
sudo eselect repository enable asahi && sudo emaint sync -r asahi   # → /var/db/repos/asahi
$EDITOR packaging/livecd/config.env
#   PROFILE        → an Asahi arm64 profile (NOT the amd64 default)
#   ASAHI_OVERLAY  → /var/db/repos/asahi
#   SNAPSHOT, STAGE3 → an arm64 snapshot + stage3-arm64 seed
sudo packaging/livecd/build.sh arm64
```

**Expect to iterate** `arm64/livecd-stage2.spec.in` (the `livecd/type`/`fstype` and
bootloader that produce a UEFI-bootable arm64 USB image) against real catalyst
output — this is the least-proven part.

### Installer gap on Apple Silicon (important)

GeST's installer runs its module steps, but its **kernel and bootloader steps are
x86-oriented**: it builds a generic kernel (genkernel/make) and runs `grub-install`.
Apple Silicon instead needs the **Asahi kernel** (`virtual/dist-kernel:asahi`) and
`update-m1n1` (from `sys-apps/asahi-scripts`) to pack m1n1 + U-Boot + the
devicetree into the EFI boot object on the ESP. So installing Gentoo *onto* an
Apple-Silicon target with GeST is **not yet complete** — you'd finish the boot
setup by hand in the target chroot per the Gentoo Asahi guide. Making GeST's
kernel/bootloader steps Asahi-aware (emerge `asahi-meta` + `dist-kernel:asahi`,
run `update-m1n1` instead of `grub-install`) is the follow-on that closes this.

### Caveats

Gentoo Asahi targets M1/M2 (M3+ unsupported), and some monthly Asahi images have
had M2 boot regressions — pin a known-good Asahi base when testing.

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
