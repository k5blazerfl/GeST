# Plan: Seamless boot — flicker-free power-on → desktop

*Status: planned (2026-08-17) · Scope: eliminate visible flicker/text across the whole amd64/systemd boot chain (power-on → GRUB → kernel → initramfs → labwc), as a sequence of implementable PRs · Implements: the boot→greeter section of [hede-systemd-stack.md](hede-systemd-stack.md) (§0, §1) · Audience: single maintainer*

> **The goal is a seamless, flicker-free transition from power-on to desktop — not
> a bootloader.** Flicker does not come from the bootloader; it comes from the
> kernel's video-mode takeover and the Plymouth → compositor handoff, both of
> which happen long after the bootloader has exited. This is **config +
> packaging + one kernel-config change + a dracut migration** — no new code, and
> **no custom bootloader** (a bootloader cannot fix a mid-kernel mode switch).

## Where we are today (verified against the tree)

Partly there already:

- `CONFIG_FRAMEBUFFER_CONSOLE_DEFERRED_TAKEOVER=y` (`packaging/livecd/amd64/kernel-config:6496`) — fbcon defers, avoiding an early clear.
- greetd autologin goes **straight to labwc with no visible greeter** (`packaging/livecd/amd64/overlay/etc/greetd/config.toml:8`) — removes one whole handoff flash.
- GPU DRM (amdgpu/i915) is deliberately deferred to post-pivot modules (`packaging/livecd/amd64/livecd-stage2.spec.in:28-35`) — avoids an early re-mode.

Working against us / missing:

- **No `quiet` / `loglevel` / `splash` on the kernel cmdline — anywhere.** The live ISO inherits catalyst's verbose default; the installer sets no `GRUB_CMDLINE_LINUX` either (`gest/core/bootloader/install.py`, `commands.py`), so installed systems boot verbose too.
- **Plymouth is completely absent** — no package, no theme, no `plymouth-quit-wait` ordering. This is the biggest gap: Plymouth is what visually bridges kernel → desktop.
- **Legacy fbdev, not simpledrm.** `FB_EFI`/`FB_VESA` are on (`kernel-config:6387-6388`) but `DRM_SIMPLEDRM`/`EFIDRM`/`VESADRM` are all off (`:6254-6256`) and `SYSFB_SIMPLEFB` is off (`:2403`). This is the older framebuffer model; the modern flicker-free path wants simpledrm so the native GPU driver can take the DRM master seamlessly at the same mode.
- **genkernel is not yet built with Plymouth**, and no `gk_mainargs`/`--plymouth` is passed — so the initramfs prints "Looking for cdrom / Mounting squashfs" text. (genkernel *can* do Plymouth; the seam just isn't wired. dracut is the committed long-term initramfs per [hede-systemd-stack.md](hede-systemd-stack.md) §0, but seamless boot does not need it first.)

## Guardrails

- **Keep GRUB.** It does flicker-free fine with `gfxpayload=keep`; no loader swap is needed for this goal. (systemd-boot remains an easy UEFI option later, per the systemd-stack doc — but out of scope here.)
- **amd64/systemd only.** The arm64 path is OpenRC-style agetty + m1n1 (`packaging/livecd/arm64/fsscript.sh`) and is out of scope; Asahi's m1n1 already does a seamless handoff.
- **Two consumers stay in sync for every cmdline change:** the **live ISO** (catalyst spec) and the **installed target** (installer bootloader code). Missing either leaves one booting verbose.

## The chain, and where each flash is born

| Stage | Flicker source | Lever |
|---|---|---|
| Firmware/GOP | OEM logo, mode set | BGRT logo preserved; mostly inherited |
| GRUB | menu draw / mode switch | `GRUB_TIMEOUT=0`, `GRUB_GFXPAYLOAD_LINUX=keep` |
| **Kernel takeover** | **EFI framebuffer → native KMS (i915/amdgpu) mode switch** | **simpledrm hands the same mode to the native driver; `quiet loglevel=3`** |
| initramfs | text spew, cursor | Plymouth started early; `rd.udev.log_level=3`, `vt.global_cursor_default=0` |
| **Plymouth → compositor** | **VT switch / black frame before first desktop frame** | **`plymouth quit --retain-splash`; labwc takes DRM master on same VT** |

The two that matter most — where nearly all real-world flicker lives — are the **kernel video-mode takeover** and the **Plymouth → labwc handoff**. The rest is one-line config.

---

## PR 1 — Quiet the boot (trivial, highest visible payoff)

Add these kernel args in **both** places:

```
quiet splash loglevel=3 rd.udev.log_level=3 vt.global_cursor_default=0 systemd.show_status=false
```

- **Live ISO:** set the **`livecd/bootargs`** spec key in `packaging/livecd/amd64/livecd-stage2.spec.in`. Catalyst prepends `livecd/bootargs` to the live kernel cmdline via `iso-bootloader-setup.sh` (this is the mapped seam — the spec sets none today, so the ISO inherits catalyst's verbose default). GRUB config on the live ISO is catalyst-generated, so the cmdline flows from `bootargs`, not from a hand-written GRUB file.
- **Installed target:** `gest/core/bootloader/` currently writes **no** cmdline. Add writing `GRUB_CMDLINE_LINUX="quiet splash loglevel=3 ..."` to `/etc/default/grub` in the chroot **before** `grub-mkconfig`. Touch points: `install.py:37-56` (pipeline) and `commands.py`. The `splash` token is harmless before Plymouth exists and is ready for PR 3.

**Test:** build ISO, boot QEMU (see the catalyst-livecd-build recipe in maintainer memory / `docs/host-validation.md`) — expect no text spew, still lands in labwc. Verify a fresh install also boots quiet.

## PR 2 — GRUB quiet & mode-stable (trivial)

```
GRUB_TIMEOUT=0            # or hidden menu
GRUB_TIMEOUT_STYLE=hidden
GRUB_GFXPAYLOAD_LINUX=keep
```

`gfxpayload=keep` hands the kernel the same video mode GRUB used → no mode flash at kernel entry.

- **Installed target:** set these in `/etc/default/grub` alongside PR 1's cmdline work — this is the main win.
- **Live ISO:** GRUB is catalyst-generated (`iso-bootloader-setup.sh` + `grub-mkrescue`, `packaging/livecd/build.sh:74-84`) and the cmdline already flows from `livecd/bootargs` (PR 1). **Theming the live GRUB menu is a separate, later step** — deprioritized; the timeout/gfxpayload levers matter most on the installed system.

**Test:** confirm no menu flash and no resolution change when the kernel takes over.

## PR 3 — Plymouth splash in the initramfs (the big one)

This is the chunk that makes it *seamless* rather than just *quiet*.

> **Decoupled from the dracut migration.** genkernel has usable Plymouth support, and catalyst already exposes the seam (`gk_mainargs` → `clst_gk_mainargs` in `kmerge.sh` → extra `genkernel` args). So the **live-CD splash uses genkernel[plymouth]** — it does *not* require migrating to dracut first. dracut remains the committed long-term initramfs ([hede-systemd-stack.md](hede-systemd-stack.md) §0), but treat that migration as an independent work stream; seamless boot must not block on it.

1. **Packages:** add `sys-boot/plymouth` to `packaging/livecd/amd64/gest.packages`, and build genkernel with the `plymouth` USE flag (`genkernel[plymouth]`). For the installed target, add `sys-boot/plymouth` to the installed-system package set / installer stage.
2. **Initramfs splash via genkernel:** set `gk_mainargs` in the stage2 spec to `--plymouth --plymouth-theme=hede`. Catalyst threads this through `kmerge.sh` into the genkernel invocation, producing a Plymouth-capable live initramfs — no initramfs rewrite required. The live initramfs still finds the squashfs/loop/iso9660 root exactly as today (those fs bits are `=y` in `kernel-config`).
3. **HeDE Plymouth theme:** author a theme from `docs/design/assets/hede-mark*.svg` (Harbor accent; nautical/Hiedi styling can come later). Two-color, static mark or subtle nautical loader; must render at the firmware resolution so there is no re-mode. Ship it via the root overlay to `/usr/share/plymouth/themes/hede/` and set it as the default theme.

**Test:** ISO boot shows the HeDE splash from early initramfs onward, no "Looking for cdrom / Mounting squashfs" text. Verify the live squashfs root still boots.

## PR 4 — simpledrm early KMS (small config change, needs HW testing)

In `packaging/livecd/amd64/kernel-config`, flip:

```
CONFIG_DRM_SIMPLEDRM=y      # currently :6255 "not set"
CONFIG_SYSFB_SIMPLEFB=y     # currently :2403 "not set"
```

This makes the firmware framebuffer a **DRM** device from boot, so Plymouth runs on DRM and the native amdgpu/i915 driver takes the DRM master **seamlessly at the same mode** — no fbdev→DRM flash. Interplay to verify:

- Keep `FRAMEBUFFER_CONSOLE_DEFERRED_TAKEOVER=y` (already on, `:6496`).
- Decide the fate of legacy `FB_EFI`/`FB_VESA` (`:6387-6388`) — with simpledrm you typically drop efifb to avoid two drivers fighting for the framebuffer. Test both ways.
- GPU DRM staying `=m` / post-pivot is fine and still desirable.

**Test:** the critical one — **real hardware** (amdgpu especially), not just QEMU. QEMU's virtio/std framebuffer won't exercise the native-driver takeover that causes real-world flicker. Watch the amdgpu-load moment specifically: it should be a seamless takeover, not a black flash.

## PR 5 — Plymouth → labwc handoff (the fiddly tuning tail)

Both Plymouth and greetd own **vt1** (`etc/greetd/config.toml:4` → `vt=1`). Sequence them so the splash stays until labwc's first frame:

- Order greetd after Plymouth in `packaging/livecd/amd64/fsscript.sh:27` — add a drop-in `After=plymouth-quit-wait.service` on `greetd.service`.
- Use `plymouth quit --retain-splash` so the splash image **stays on screen** through the DRM-master hand to labwc — no black frame, no VT switch.
- labwc likely becomes the thing that finally clears the retained splash on first frame; tune `--retain-splash` vs. a short quit delay.

> Note: [hede-systemd-stack.md](hede-systemd-stack.md) §1 envisions replacing greetd with HeDE's *own* Wayland greeter unit. The current tree still uses **greetd autologin → labwc** (`config.toml`, `hede/src/session/helm-session:19-28`). This plan targets the greetd-as-shipped path; if/when the own-greeter lands, the same `After=plymouth-quit-wait` + `--retain-splash` ordering applies to that unit instead.

**Test:** slow-motion phone video of the final transition — the retained splash should dissolve directly into the labwc desktop with zero black frames.

---

## Sequencing & risk

| PR | Effort | Risk | Payoff |
|---|---|---|---|
| 1 quiet cmdline | ~1h | very low | huge (kills text spew) |
| 2 GRUB config | ~1h | very low | no mode flash at kernel entry |
| 3 Plymouth splash (genkernel) | ~1 day | medium (theme + genkernel[plymouth]) | the actual splash bridge |
| 4 simpledrm | ~½ day + HW test | medium (HW-dependent) | seamless GPU takeover |
| 5 retain-splash handoff | tuning tail | medium | glass-smooth final transition |

- **Recommended first slice** (matches the mapped work stream): **PR 1 + PR 3 on the live CD** — quiet cmdline via `livecd/bootargs` plus a basic Helm Plymouth theme via genkernel. Iterable in QEMU. Defer the GRUB menu theming and the installer track.
- **PRs 1–2 are independently shippable** and give a dramatic improvement for an afternoon.
- **PR 4 must be validated on real amdgpu hardware**, not just QEMU.
- Two tracks throughout: **(1)** the live CD (fast QEMU loop) and **(2)** the installer's bootloader step configuring the same for installed systems.

## Open decisions

1. **genkernel[plymouth] now vs. dracut later** — this plan uses genkernel[plymouth] for the splash to avoid coupling seamless boot to the dracut migration. Confirm that's the intent (recommended), and that the dracut migration ([hede-systemd-stack.md](hede-systemd-stack.md) §0) proceeds on its own track and simply re-homes the same Plymouth theme when it lands.
2. **Keep efifb alongside simpledrm, or drop it?** — test-driven; note the outcome in PR 4.
3. **Plymouth theme style** — static mark vs. subtle animation. Static is safest for "no re-mode."
4. Whether to also link this plan from [hede-systemd-stack.md](hede-systemd-stack.md) "Follow-on work" as the implementation checklist for its boot→greeter section.
