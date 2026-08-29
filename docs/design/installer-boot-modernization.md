# Design: GeSI boot-path modernization

Today GeSI builds the boot path the classic Gentoo way: **`genkernel`** compiles
`sys-kernel/gentoo-sources` (with a curated per-arch config, `--plymouth` for the
HeDE splash), and **GRUB** boots it. It works, but the kernel is the one
source-compiled step in an otherwise binary install, and the bootloader is heavier
than a modern UEFI system needs.

This plan modernizes the path in three phases, hinged on **`installkernel`** — the
mechanism dist-kernels use to place the kernel image and (re)generate the initramfs
via **dracut**. Adopting installkernel + dracut is what unlocks both a binary
kernel (Phase 2) and a lean bootloader (Phase 3).

## Current state

- Kernel: `genkernel all` on `gentoo-sources` — compiles from source, bakes the
  initramfs (Plymouth splash baked in via `--plymouth`), rebuilt after the NVIDIA
  module lands for early KMS.
- Bootloader: GRUB (`grub-install` + `grub-mkconfig`), the HeDE Harbor theme staged
  into `/boot/grub/themes/hede`.
- Recovery: the install run is a plan of idempotent steps.

## Phase 1 — graceful in-run recovery ✅ (shipped, PR #209)

The install engine recovers gracefully from a transient step failure instead of
aborting the whole run — retry/skip semantics so a flaky mirror or a re-run doesn't
strand a half-installed target. Independent of the kernel/bootloader work; done.

## Phase 2 — dist-kernel (binary kernel)

Replace the compile-every-time `genkernel`/`gentoo-sources` path with the
**distribution kernel** `sys-kernel/gentoo-kernel-bin` (prebuilt, installed from a
binpkg — no local compile), initramfs via `installkernel` → **dracut**. This makes
a *binary* install binary all the way (the kernel stops being the odd source-built
step). It does **not** eliminate the NVIDIA out-of-tree module build — `nvidia_drm`
still compiles against the bin kernel's headers via `@module-rebuild` (same early-KMS
step as today), that's an irreducible cost on the proprietary stack.

The migration splits cleanly by whether the install needs HeDE's seamless boot,
because that is the *only* thing that ties the kernel to genkernel:

### Phase 2a — dist-kernel for non-HeDE binary installs (drop-in, first)

A base-Gentoo (non-HeDE) install has **no Plymouth splash, no seamless boot, no
tuned-config requirement** — so nothing couples it to genkernel. Switch it to
`gentoo-kernel-bin` + a plain dracut initramfs and it's a **drop-in**: zero compile,
instant kernel, binary end-to-end. This is the isolated, low-risk win and should
land first.

- **Gate**: `binary_pref and not plan.desktop` (both already tracked by the wizard)
  selects a new `dist` kernel method on `BuildConfig.method` (alongside `genkernel`
  / `make`).
- **Initramfs**: dracut default (no Plymouth) — a base install needs nothing special.
- **Untouched**: source-strategy installs keep `genkernel`/`gentoo-sources` (tuned);
  HeDE stays on genkernel until 2b.

### Phase 2b — dist-kernel + dracut-Plymouth for HeDE binary installs

HeDE's seamless splash is currently **baked into the initramfs by `genkernel
--plymouth`**. `gentoo-kernel-bin` generates its initramfs via dracut, so keeping the
biome splash means teaching **dracut to include Plymouth + the HeDE theme** (a
dracut module/config), plus carrying the NVIDIA early-KMS module into that dracut
initramfs. Once that path exists, HeDE binary installs move to the bin kernel too
and the seamless boot is preserved. Until then, HeDE has a *real* reason to stay on
genkernel — it's the only install flavor that does.

- **Depends on**: the biome-splash-on-dracut work (see
  [hede-boot-background.md](hede-boot-background.md) — the Plymouth stage there moves
  from a genkernel bake to a dracut module).
- **Gate**: `binary_pref and plan.desktop` selects `dist` once 2b lands.

## Phase 3 — systemd-boot

Replace GRUB with **systemd-boot** on UEFI targets: a lean EFI stub boot manager,
no `grub-mkconfig`, kernels dropped as Boot Loader Spec entries by `installkernel`.
Simpler, faster, and a natural fit once installkernel/dracut is the kernel hinge
(Phase 2). GRUB stays for BIOS and as the themed fallback; the Harbor GRUB theme and
the biome-background chain ([hede-boot-background.md](hede-boot-background.md)) carry
over where GRUB is still used. (BIOS installs keep GRUB regardless.)

## The installkernel hinge

`installkernel` is the shared pivot: dist-kernels (Phase 2) install through it, and
systemd-boot (Phase 3) consumes its Boot Loader Spec entries. Standardizing the
kernel-install seam on `installkernel` + dracut is what lets 2 and 3 compose instead
of each being a bespoke rewrite.

## Non-goals

- **Forcing dist-kernel on source-strategy installs** — "compile from source" is a
  deliberate Gentoo choice; it keeps `genkernel`/`gentoo-sources`.
- **Dropping GRUB on BIOS** — systemd-boot is UEFI-only; BIOS keeps GRUB.
- **Eliminating the NVIDIA module compile** — out-of-tree, irreducible on the
  proprietary stack even with a binary kernel.
