# GeSI vs. `oddlama/gentoo-install` — competitive gap analysis

Status: **R&D reference**, 2026-08-22. A capability comparison against the most
mature community Gentoo installer, done to find (a) where GeSI already leads and
should keep pressing, (b) real gaps worth closing, and (c) mechanisms worth
borrowing outright. Not a plan of record — feeds [[gesi-disk-phase]] and the
robustness backlog.

## What oddlama is

[`oddlama/gentoo-install`](https://github.com/oddlama/gentoo-install) is ~5 pure
Bash scripts (ShellCheck-linted, VM-tested) driven by a menuconfig-style TUI that
writes a **sourced-bash config file** (`gentoo.conf`). It runs from *any* live
environment (it auto-installs its own host dependencies via the detected package
manager) and, after a single sanity gate, installs **unattended**. Partitioning
is `sgdisk` GPT-only. Its whole thesis is **flexible storage topology + a
declarative, unattended config** — deliberately the opposite axis from GeSI's
*reviewed-wizard* thesis. It ships a base system + optional SSH and stops there:
no users, no desktop, no USE/profile policy.

Key files: `scripts/config.sh` (disk-layout DSL), `scripts/functions.sh`
(storage/kernel/net implementation), `scripts/main.sh` (phase order),
`scripts/utils.sh` (`try`/`ask`/`countdown`/arg parser), `gentoo.conf.example`.

## Capability matrix

| Area | oddlama | GeSI | Verdict |
|---|---|---|---|
| Storage topology | LUKS2, mdraid 0/1/5/6, ZFS (native enc), btrfs-raid, **composable DSL** | Single-disk GPT guided only; LUKS/LVM/RAID designed, **not built** | **oddlama leads big** |
| LVM | ❌ none | ❌ none (planned) | tie (both gap) |
| Filesystems (root) | ext4, btrfs, zfs | ext4, ext3, xfs, btrfs, f2fs | **GeSI leads** |
| Bootloader | EFISTUB + `efibootmgr` / syslinux (BIOS) | **GRUB** (UEFI + BIOS), seamless theme | different philosophy |
| Secure Boot | ❌ | ❌ | tie |
| Init system | systemd/OpenRC (from stage3) | systemd-first, both; HeDE = systemd | tie |
| Kernel / initramfs | `gentoo-kernel[-bin]` + **dracut only** | genkernel/make **from source**; curated virtio configs | oddlama has dist-kernel + dracut; **GeSI lacks both** |
| Stage3 verify | GPG + hash | **BLAKE2B + SHA512 mandatory** (refuses on mismatch) + GPG | **GeSI leads** |
| USE / profile / CFLAGS | ❌ none (stage3 defaults) | capability→USE policy, `CPU_FLAGS_X86` probe, `-march=native`, `eselect profile` per role | **GeSI leads big** |
| `ACCEPT_LICENSE` | one firmware line only | **3-rung policy** (libre / redistributable / full) | **GeSI leads big** |
| Accounts / sudo | ❌ **root-only**, no user, no sudo | **3-axis admin model** (traditional / sudo-aug / rootless) + wheel user + sudo/doas, safety invariant | **GeSI leads big** |
| Networking | systemd-networkd / dhcpcd | **netifrc** ⚠️ (contradicts NM standardization) | oddlama more coherent; **GeSI defect** |
| Timezone / locale | runs locale generation | offline lists, but **`locale-gen` never run**, pinned `C.UTF-8` | **oddlama leads** (GeSI open bug) |
| Roles / profiles | ❌ none (bash hooks only) | Desktop/Server/Minimal/Custom coherent proposals | **GeSI leads big** |
| Desktop provisioning | ❌ base + SSH only | **full HeDE offline install** (quickpkg + overlay seed), GPU auto-detect | **GeSI leads big** |
| Flow model | flat config + unattended | **7-gate wizard + frozen diffable `InstallPlan` + review gate** | **GeSI leads** (UX/safety) |
| Recovery UX | **`try()` interactive retry/shell/abort loop** | stop-at-first-failure + resumable `is_satisfied` steps | oddlama nicer UX; GeSI more idempotent |

## Where GeSI already leads (keep pressing, don't chase oddlama)

- **Role-proposed coherent config.** A role proposes a whole consistent set
  (build strategy, license rung, admin model, GPU policy, day-2 services, USE
  features); later gates edit real defaults with `•changed` markers. oddlama has
  no roles at all.
- **3-axis account/admin model** (traditional / sudo-augmented / rootless) with a
  "never ship a system you can't administer" invariant. oddlama is **root-only**
  — no user creation, no sudo/doas.
- **Capability→USE policy + 3-rung `ACCEPT_LICENSE`.** oddlama leaves USE,
  profile, and CFLAGS at stage3 defaults and writes one firmware license line.
- **Reviewed, diffable `InstallPlan`** — the whole run is a frozen, inspectable,
  unit-testable value approved at a review gate before any step touches a disk;
  secrets deliberately excluded so plans are safe to log.
- **Enforced cryptographic stage3 verification** (BLAKE2B + SHA512, refuses to
  unpack on mismatch) — stronger and non-optional vs. oddlama's GPG+hash.
- **A real desktop.** Full HeDE offline provisioning + GPU auto-detect. oddlama
  installs a base system + optional SSH and stops.

These are genuine, defensible differentiators. The reviewed-wizard thesis is the
product; oddlama's config-as-bash/unattended model is a conscious non-goal.

## Gaps worth closing (ranked)

1. **Storage topology (LUKS / LVM / RAID / ZFS)** — oddlama's biggest lead and
   GeSI's biggest hole. This is the [[gesi-disk-phase]] work. Borrow the shape:
   oddlama's **composable disk DSL** (`create_partition` / `create_raid` /
   `create_luks` / `format` primitives behind a validated named-arg parser) is a
   clean, testable way to express arbitrary topologies and maps directly onto the
   guided-proposal + manual-fork `StoragePlan` design. Specific details worth
   lifting: **RAID metadata 1.0 on the EFI/RAID1 array** (so firmware can still
   read the ESP), LUKS2 argon2id defaults, and **dropping a LUKS header backup +
   an initramfs-regen script into the target**.
2. **`try()` interactive recovery loop** — on any step failure, offer
   *shell / retry / abort / continue*, then resume the exact step. High-payoff UX
   for the ~30-line `run_install` engine, and it composes with the existing
   resumable `is_satisfied` model rather than replacing it.
3. **`locale-gen` not invoked** — GeSI writes `/etc/locale.conf` +
   `/etc/env.d/02locale` but never generates the locale, so the default is pinned
   to `C.UTF-8`. oddlama generates locales; this is an already-tracked open bug
   and the fix unblocks `en_US.UTF-8` as the default.
4. **Installed-system networking is netifrc** — inert on systemd and in direct
   conflict with the project-wide NetworkManager standardization
   ([[gest-network-networkmanager]]). A default systemd install can boot with no
   network. oddlama went systemd-networkd; either fix is coherent, but GeSI's
   current state is the actual defect. **Highest-correctness item.**
5. **dist-kernel + dracut option** — oddlama offers `gentoo-kernel-bin` + dracut;
   GeSI is genkernel/make-from-source only. A binary-kernel path would massively
   cut install time and pairs naturally with the binary build strategy.
6. **Symbolic device-ID resolution** — oddlama resolves stable `DISK_ID_*` →
   UUID → real block device, avoiding `/dev/sdX`-reordering / wrong-disk bugs. A
   cheap safety win for the disk engine.
7. **Per-phase `before_/after_` hooks** — extensibility without forking the
   installer. Nice-to-have, lower priority.

## Conscious non-goals (do not borrow)

- **Config-as-bash + unattended** — opposite of the reviewed-wizard thesis.
- **ZFS** — a large lift with low payoff for the HeDE audience; behind LUKS/RAID.
- **Secure Boot** — neither installer does it; not a near-term differentiator.
