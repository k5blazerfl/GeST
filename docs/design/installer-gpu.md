# Installer GPU driver + firmware support

How GeSI gives an installed system a working GPU driver stack — in particular the
**NVIDIA proprietary** stack a modern GeForce card needs for a Wayland/HeDE desktop.

## The gap this closes

Before this, the installer had **no GPU-driver path at all**: `WriteMakeConf` wrote
only `MAKEOPTS`, `VIDEO_CARDS` was never set, no `linux-firmware` was installed, and
no driver was emerged. On an NVIDIA card the installed system fell back to nouveau
with no GSP firmware, so `labwc`/wlroots (HeDE's Wayland session) could not start —
a black or unaccelerated desktop on first boot. GPU *detection* existed
(`gest/core/hwflags/detect.py`) but only as a standalone settings editor, never wired
into the install.

## The model — `GpuSpec`

`plan.py` carries a frozen `GpuSpec` on the `InstallPlan`:

| field | meaning |
| --- | --- |
| `video_cards` | the `VIDEO_CARDS` tokens for make.conf (`("nvidia",)`, `("amdgpu", "radeonsi")`, …) |
| `nvidia_proprietary` | install `x11-drivers/nvidia-drivers` (license + module + KMS + nouveau blacklist) instead of nouveau |
| `kernel_open` | build nvidia-drivers with the **open** kernel modules (`USE=kernel-open`) — NVIDIA-recommended for Turing+/Ada; off by default (unsupported pre-Turing), only meaningful with `nvidia_proprietary` |
| `nvidia_slot` | the nvidia-drivers **SLOT** for a legacy branch — `"0/470"` (Kepler) or `"0/390"` (Fermi); empty = the current/default slot. When set, the driver atom is slotted and GeST writes a `package.unmask` (the legacy slots are masked upstream). `kernel_open` is never set for a legacy slot. |

`nvidia_proprietary` implies a `nvidia` token (added in `assemble._build_gpu`), so
asking for the proprietary stack is self-contained.

### Detection (`assemble.resolve_gpu`)

The peer of `resolve_stage3`: it runs `lspci` (I/O) via `hwflags.detect` and returns a
`GpuSpec`. The TUI installer calls this at install time unless the user overrode the
choice (`InstallSelections.gpu_auto`), so a detected card is handled hands-off.

**NVIDIA driver branch by architecture.** NVIDIA splits its closed driver by GPU
generation, and Gentoo ships each as a separate SLOT of `x11-drivers/nvidia-drivers`.
`hwflags.detect.nvidia_driver_branch` reads the chip **codename** in the `lspci` line
(`GK107`, `GF119`, `AD103`, …) — the two-letter prefix encodes the architecture — and
maps it to a branch:

| codename prefix | arch | branch | driver |
| --- | --- | --- | --- |
| `AD` `GB` `GA` `TU` | Ada / Blackwell / Ampere / Turing | `current` + `kernel_open` | `nvidia-drivers` (open modules) |
| `GV` `GP` `GM` | Volta / Pascal / Maxwell | `current` | `nvidia-drivers` (closed modules) |
| `GK` | Kepler | `legacy-470` | `nvidia-drivers:0/470` (+ unmask) |
| `GF` | Fermi | `legacy-390` | `nvidia-drivers:0/390` (+ unmask) |
| `G8x` `G9x` `GT2xx` | Tesla and older | `nouveau` | none — `VIDEO_CARDS=nouveau` |

The open kernel modules are chosen only for Turing-or-newer (NVIDIA-recommended; it
sidesteps closed-module IBT issues on kernels built with `CONFIG_X86_KERNEL_IBT`). A
Kepler/Fermi card gets its legacy slot **plus** a `package.unmask/gest-gpu` (those slots
are masked by the Gentoo profile). Tesla-and-older have no supported in-tree proprietary
driver (the 340 branch is gone), so they fall back to nouveau, firmware-only. An NVIDIA
card whose codename `lspci` doesn't spell out falls back to `current` (the common case is
a newer card); a genuinely old unrecognized card can be switched to nouveau in the UI.

**AMD legacy.** Pre-GCN (TeraScale) chips — matched by codename/family
(`amd_legacy_radeon`) — get `VIDEO_CARDS="radeon r600"` instead of the default
`amdgpu radeonsi`, since the modern `amdgpu` kernel driver doesn't support them.

**Hybrid graphics** (e.g. a Ryzen X3D's RDNA2 iGPU alongside a discrete GeForce) are
handled naturally: `detect_video_cards` accumulates every GPU, so `VIDEO_CARDS` gets
both `amdgpu radeonsi nvidia`; the presence of NVIDIA still selects the proprietary
stack, and the NVIDIA-only hardening never touches amdgpu/i915.

### User override

The installer overview's **Graphics** row edits the choice: auto-detect (default),
NVIDIA proprietary, nouveau, a custom `VIDEO_CARDS` string, or none (firmware only),
plus an *open kernel modules* checkbox (`kernel_open`, applied only to the NVIDIA
proprietary choices). Picking anything but auto sets `gpu_auto = False`, so the
RunScreen skips detection and takes the selection as-is.

## The install steps

1. **`WriteMakeConf`** (base-system phase, before `@world`) also writes `VIDEO_CARDS`,
   so mesa/xorg and everything in `@world` build with the right driver USE.
2. **`InstallGpuDrivers`** (kernel-&-boot phase, **after `BuildKernel`**, before
   `InstallBootloader`) — pure builders in `gest/core/install/gpu.py`:
   - accept the licenses the atoms need (`linux-fw-redistributable`, and `NVIDIA-r2`
     when proprietary) via `package.license/gest-gpu` — else the emerge is masked;
   - **always** emerge `sys-kernel/linux-firmware` (fixes the general no-firmware gap —
     GSP, Wi-Fi, etc. — not just NVIDIA);
   - when proprietary: emerge `x11-drivers/nvidia-drivers`, then `@module-rebuild`;
     with the open kernel modules requested (`GpuSpec.kernel_open`), first write
     `package.use/gest-gpu` with `x11-drivers/nvidia-drivers kernel-open`;
   - write `/etc/modprobe.d/gest-gpu.conf` — `blacklist nouveau` + `options nvidia_drm
     modeset=1 fbdev=1`;
   - merge the nouveau blacklist + `nvidia_drm.modeset=1` into `GRUB_CMDLINE_LINUX`
     (`/etc/default/grub`) — see *Ordering* below.

AMD/Intel need no extra package here: their kernel drivers are in-tree (modules) and
mesa comes from `@world`/the desktop keyed on `VIDEO_CARDS`; they only need the
firmware this step installs.

## Ordering — why the driver is late, and why the cmdline is needed

`nvidia-drivers` is an out-of-tree kernel module, so it must build against a **built**
kernel — hence `InstallGpuDrivers` runs *after* `BuildKernel`. But that means the
**initramfs is already built** before nouveau is blacklisted, so a `modprobe.d` file
(read from the real root, post-pivot) cannot stop nouveau binding the card during early
boot. The fix is to put the blacklist + modeset on the **kernel cmdline**
(`rd.driver.blacklist=nouveau modprobe.blacklist=nouveau nvidia_drm.modeset=1
nvidia_drm.fbdev=1`), which the bootloader reads from the very first stage.
`InstallGpuDrivers` merges these into `/etc/default/grub` (idempotent, append-dedup)
*before* `InstallBootloader` runs `grub-mkconfig`, and the seamless-boot writer
preserves them (it only manages `GRUB_CMDLINE_LINUX_DEFAULT`).

## The framebuffer / boot flow

- **Early boot (initramfs, before any GPU driver):** the shipped kernel config has
  `CONFIG_FB_EFI=y`, so UEFI systems get an EFI framebuffer that Plymouth renders the
  splash on. (`CONFIG_DRM_SIMPLEDRM` was considered, but the config builds DRM
  modular — `CONFIG_DRM=m` — so simpledrm can't be built-in, and its EFI handover needs
  `CONFIG_SYSFB_SIMPLEFB`, which isn't set; efifb already covers the early framebuffer,
  so simpledrm is not pursued.)
- **After pivot:** the real DRM driver loads as a module from the root — `amdgpu` /
  `i915` (in-tree), or `nvidia_drm` with `modeset=1` — and takes over KMS. wlroots/labwc
  then has a DRM+GBM device and HeDE starts.

## Per-vendor summary

| GPU | `VIDEO_CARDS` | extra emerge | modprobe.d / cmdline | notes |
| --- | --- | --- | --- | --- |
| NVIDIA Turing+ (RTX 20+/GTX 16) | `nvidia` | `nvidia-drivers` (open) + `@module-rebuild` | yes (blacklist + modeset) | open kernel modules |
| NVIDIA Maxwell–Volta (GTX 9xx/10xx) | `nvidia` | `nvidia-drivers` (closed) + `@module-rebuild` | yes | current slot, closed modules |
| NVIDIA Kepler (GTX 6xx/7xx) | `nvidia` | `nvidia-drivers:0/470` + unmask + `@module-rebuild` | yes | legacy 470 branch |
| NVIDIA Fermi (GTX 4xx/5xx) | `nvidia` | `nvidia-drivers:0/390` + unmask + `@module-rebuild` | yes | legacy 390 branch |
| NVIDIA Tesla & older (8/9/2xx) | `nouveau` | — | no | no proprietary driver in-tree |
| AMD GCN+ | `amdgpu radeonsi` | — | no | in-tree amdgpu + mesa; firmware only |
| AMD pre-GCN (TeraScale) | `radeon r600` | — | no | in-tree radeon + mesa; firmware only |
| Intel | `intel` | — | no | in-tree i915 + mesa; firmware only |
| hybrid (AMD/Intel + NVIDIA) | both | per NVIDIA branch | yes (NVIDIA-only) | iGPU coexists with the dGPU |
| none / undetected | — | — | no | firmware only |

## Known follow-ups

- **Early-KMS firmware in the initramfs** for a seamless amdgpu/i915 splash *before*
  the pivot. Deferred: genkernel's `--firmware` bundles all of `/lib/firmware` (huge
  initramfs) and targeted bundling needs exact per-ASIC filenames; the post-pivot path
  works with the root firmware this feature installs, and efifb covers the early splash.
- **Real-hardware validation** on the Ryzen 9900X3D / RTX 4070 Ti Super rig — the
  intended first end-to-end test.
