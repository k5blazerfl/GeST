# Roadmap: the module foundation before the installer

*Status: roadmap · Scope decision: Tier 1 + Tier 2 · Defers: Tier 3 and the system installer*

## Why this comes first

The end goal for the CLI is to facilitate a full Gentoo install. But an installer
is not a new program — it is an **orchestration over the same modules** GeST
already uses to administer a running system, pointed at a target root under
`/mnt/gentoo` instead of `/`. Every install step (partition, mkfs, stage3,
configure `/etc/portage`, build a kernel, install a bootloader, set root's
password) is a module operation.

So the modules *are* the foundation. Completing them as live-host administration
modules — following the existing `model / reader / commands / backend_client`
convention, gated through the polkit D-Bus backend — both finishes GeST as a
standalone admin tool **and** produces every subsystem the installer will later
sequence. The installer becomes a thin flow on top, once each module learns a
target-root parameter (see [Forward-compatibility](#forward-compatibility-with-the-installer)).

This doc enumerates the complete module surface, marks what exists, and defines
the foundation as **Tier 1 + Tier 2**. Tier 3 and the installer are explicitly
out of scope here.

## What already exists (the config half)

All polkit-gated through the D-Bus backend, all following the per-module
convention:

- **Software**: install/remove/update (`@world`), depclean, tree sync, news,
  world/sets, repos/mirrors/binhost/licenses, `make.conf` + per-package
  USE/keywords/mask, CPU/VIDEO flags. Declared complete.
- **eselect**: generic module/target browser — **profile selection already
  works** as a row in the module list (no dedicated UI, but the operation exists).
- **System**: hostname, timezone, locale. **Date/time/NTP**.
- **Users**: add/edit/delete, passwords (incl. root), group membership
  (so `wheel` works via the generic path).
- **Services**: OpenRC enable/disable/start/stop.
- **Storage**: read `lsblk`, **edit** `/etc/fstab`, mount/unmount.
- **Bootloader**: regenerate `grub.cfg`. **Logs** viewer.

Status legend below: ✓ done · ◐ partial · ✗ missing.

## Tier 1 — install-path foundation

The provisioning subsystems. These are the biggest current gaps, and the ones
the installer orchestrates most directly. Each becomes a module with a reader
(unprivileged query) and a new backend RPC + polkit action.

| Module | Status | Tools to wrap | New backend surface |
|---|---|---|---|
| **Storage provisioning** | ✗ | `parted`/`sgdisk`, `mkfs.*`, `mkswap`/`swapon`, `cryptsetup`, `lvm`, `mdadm` | `org.gentoo.gest.Disk` gains `Partition`, `MakeFilesystem`, `MakeSwap`/`SwapOn`, plus optional LUKS/LVM/RAID methods; new polkit actions per class of destructive op |
| **Kernel build** | ✗ (read-only) | `genkernel` / `dracut` (initramfs), `make`/`installkernel`, module signing | new `org.gentoo.gest.Kernel` interface: `Configure`, `Build`, `Install` — streamed like emerge |
| **Bootloader install** | ◐ (config regen only) | `grub-install`, `efibootmgr`, `bootctl` | extend `org.gentoo.gest.Bootloader`: `Install`, `AddEfiEntry` alongside `RegenerateGrub` |
| **Console keymap/font** | ✗ | writes `/etc/conf.d/keymaps`, consolefont | extend `org.gentoo.gest.System`: `SetKeymap`, `SetConsoleFont` |
| **DNS + hosts** | ✗ | writes `/etc/resolv.conf`, `/etc/hosts` | new methods on `System` or `Network`: `SetResolvers`, `SetHosts` |

Notes:
- **Storage provisioning is the single largest net-new subsystem.** It is also
  the most dangerous — `mkfs` on the wrong device destroys data. The backend
  must enforce a device allow-list per operation (never operate on a mounted
  device or the running root) with the same rigor the disk module already applies
  to protecting `/`, `/boot`, `/efi`, swap in fstab.
- **Kernel build** streams long output — reuse the `runscreen.py` streaming-
  progress base, exactly as emerge does.
- **fstab generation** (from a partition plan) is a small addition on top of the
  existing fstab editor once storage provisioning lands — not a separate module.

Already-present install-path pieces (no work needed, just wiring into the eventual
flow): profile via eselect, root password via users, timezone/locale/hostname,
make.conf/USE/flags, repos/sync/world install, fstab editing.

## Tier 2 — day-2 admin essentials

Not strictly install-critical, but required for GeST to be a complete standalone
administration tool. Each is a small module in the established pattern.

| Module | Status | Tools to wrap | Config surface |
|---|---|---|---|
| **Firewall** | ✗ | `nft` (nftables) | `/etc/nftables.nft`; enable service |
| **sshd server config** | ✗ | edit `sshd_config` | `/etc/ssh/sshd_config` (client deploy-key already exists, separately) |
| **cron / scheduled tasks** | ✗ | `crontab`, drop-ins | `/etc/cron.*`, user crontabs |
| **sudo/doas config** | ✗ (wheel membership only) | edit sudoers/doas.conf | `/etc/sudoers.d/`, `/etc/doas.conf` |
| **sysctl** | ✗ | `sysctl` | `/etc/sysctl.d/` |
| **env.d editor** | ◐ (writes `02locale` only) | `env-update` | `/etc/env.d/` general editor |
| **Wi-Fi** | ✗ | `wpa_supplicant` / `iwd` | complements the wired-only netifrc module |

Notes:
- **sudo/doas** deserves care: today `wheel` membership works but no privilege-
  escalation policy is written. A minimal, reviewable diff (uncomment
  `%wheel ALL=(ALL:ALL) ALL`, or a `doas.conf` line) is the right scope.
- **env.d** should generalize the existing `02locale` write path rather than add
  a parallel writer — same lesson as the portage-config-core unification.

## Tier 3 — deferred (out of scope here)

Printers (CUPS), sound (ALSA/PipeWire), bluetooth, NFS/Samba client, VPN, backup,
btrfs snapshots, power management, certificates/CA trust. These are desktop/server
conveniences unrelated to installing or bootstrapping a system. Revisit after the
foundation and installer land.

## Beyond the foundation — desktop-era module design docs

Modules that arrive with **HeDE** and are gated behind the Qt frontend (they are
*not* install-path work, and land after this foundation and the frontend). Each
already has a full design doc; indexed here so the module surface stays in one
place:

- [**Keychain**](keychain.md) — GeST/HeDE *becomes* the freedesktop Secret
  Service provider (`org.freedesktop.secrets`): a vault + a session daemon
  (`helm-keyringd`) + a management module. GeST's first *session-bus server*
  (vs. the usual client-of-root-backend pattern); no gnome-keyring/kwallet dep.
- [**Windows interop (RDP + Wine/Proton)**](hede-windows-interop.md) — two
  switcher-facing HeDE modules over a shared foreign-app integration layer:
  **Gangway** (remote Windows via FreeRDP) and **Drydock** (local Windows apps
  via Wine/Proton), the latter driving USE/`make.conf` prereqs through the same
  polkit'd Software path these foundation modules already use. Gangway consumes
  Keychain for credential storage.

## Forward-compatibility with the installer

Build every Tier 1/Tier 2 module against the **live host now**, but with one
design constraint that makes the installer nearly free later:

- **Thread a target root through paths, not logic.** The portage core already
  honours `portage.settings["PORTAGE_CONFIGROOT"]` (`portage/paths.py`). Extend
  that discipline: every module's writer resolves its target files under a
  configurable root (default `/`), and every command builder can be wrapped for
  `chroot <root>` / `emerge --root=<root> --config-root=<root>`. Then the
  installer is a flow that sets the root to `/mnt/gentoo` and calls the same
  modules in Handbook order.
- **Do not fork provisioning logic for install vs. maintenance.** `mkfs` a spare
  disk on a running system and `mkfs` a target partition during install are the
  same operation with a different device argument. Keep them one code path.

This is why "modules first" is the correct sequencing, not a detour: the
foundation work and the installer's prerequisites are the same work.

## Sequencing

Roughly by dependency and payoff:

1. **Storage provisioning** — the biggest gap, blocks the most (fstab gen,
   installer, LVM/LUKS). Start with `mkfs`/`mkswap`/`swapon` and partitioning;
   layer LUKS/LVM/RAID after.
2. **Kernel build** — unblocks a bootable system; high user value standalone
   (kernel upgrades on a running box).
3. **Bootloader install** — completes the boot path; small once kernel lands.
4. **Console keymap/font + DNS/hosts** — small `System`/`Network` extensions.
5. **Tier 2** in any order — each is independent and independently shippable:
   firewall, sshd, cron, sudo/doas, sysctl, env.d, Wi-Fi.

Each module is independently shippable and testable, matching the release cadence
GeST already runs on.

## Testing

Follow the established patterns:
- **Readers** with injected `Runner`/paths over fixture trees (the
  `datetime/reader.py` pattern).
- **Command builders** as pure argv tests.
- **Backend contract** tests for every destructive op: device/path allow-listing
  rejects operating on mounted/running targets; server-side re-validation; no
  partial state on failure (the `_atomic_write_file` temp-cleanup assertion
  pattern, extended to device operations where a dry-run/`--pretend` exists).

## Non-goals

- The system installer itself (a later track, built on this foundation).
- systemd support (out of scope per the roadmap; OpenRC only).
- Tier 3 desktop/server modules.
- The Qt/KDE frontend (gated until the TUI/CLI side is declared complete).
