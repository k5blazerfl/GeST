# Design: storage provisioning (the partitioner)

*Status: proposal · Target: `gest/core/disk/` (extended) + `org.gentoo.gest.Disk` · Depends on: [runtime-privilege-path](runtime-privilege-path.md) · First Tier-1 module per the [module-foundation roadmap](module-foundation.md)*

## Why

The disk module today is **read-only plus fstab**: it parses `lsblk -J`, edits
`/etc/fstab`, and mounts/unmounts already-defined targets (protecting `/`,
`/boot`, `/efi`, swap). It never creates anything. Storage provisioning —
partition a disk, make filesystems, make and enable swap — is the single largest
gap in the install path and the first module built, because it blocks the most:
fstab *generation*, the installer flow, and later LUKS/LVM/RAID.

It is also the most dangerous code in GeST: `mkfs` or `sgdisk` on the wrong
device destroys data irreversibly. The design therefore leads with the safety
model, not the feature list. It is tested from a **Gentoo live CD on a separate
machine** against real wipeable disks (see the live-CD testing note), which is
why it must run under the `DirectExecutor` already-root path from
[runtime-privilege-path](runtime-privilege-path.md).

## Scope

**v1 (this doc's core):**
- **Partition** — GPT via `sgdisk` (scriptable; preferred over interactive
  `parted`/`fdisk`). Create the Handbook's typical layout: EFI system partition
  (`EF00`), optional swap (`8200`), root (`8300`).
- **Filesystems** — `mkfs.vfat` (EFI), `mkfs.ext4`/`xfs`/`btrfs`/`f2fs` (root),
  with label support.
- **Swap** — `mkswap` + `swapon`/`swapoff`.
- **fstab generation** — emit `/etc/fstab` entries from the applied plan (UUID-
  based), reusing the existing fstab writer.

**Later (layered on the same module, separate docs/PRs):**
- **LUKS** — `cryptsetup luksFormat`/`open`, mapping into the plan.
- **LVM** — `pvcreate`/`vgcreate`/`lvcreate`.
- **RAID** — `mdadm --create`.

MBR/BIOS layouts are a follow-on; v1 targets GPT/UEFI as the default.

## Safety model — the part that matters

Destructive operations name a device or partition. Before running anything, the
**runner re-validates** every target (the frontend's checks are convenience; the
runner's are the contract — the same discipline as the portage backend's path
allow-listing):

- **Must be a real block device** (`/dev/*`, resolves via `realpath`, present in
  the `lsblk` tree).
- **Must not be mounted** — cross-check `/proc/mounts`. The one exception is a
  device the current plan is *building* (e.g. formatting the root partition just
  created), which is explicitly part of the reviewed plan, not an already-live
  mount.
- **Must not be the running root, an active swap, or the live medium** — refuse
  the disk the live CD booted from and anything backing `/`. This is the live-CD
  equivalent of the installed module protecting `/`, `/boot`, `/efi`.
- **Whole-disk wipe requires typed confirmation** — the UI shows the current
  partition table vs. the planned one (the diff-preview pattern the Software UI
  already uses for config), and the user types the device name to confirm, à la
  every serious partitioner.

Where a tool offers a dry run, use it in preview: `wipefs -n`, `sgdisk --print`,
`mkfs -N` (ext) to show what *would* happen before the real run.

## The declarative plan (a value type, not a verb soup)

Rather than N imperative RPCs the UI calls in sequence, the core builds a
reviewable **`DiskPlan`** — the `ConfigWrite`/preview pattern applied to storage:

```python
@dataclass(slots=True, frozen=True)
class Partition:
    number: int
    size: str           # "512M", "8G", "rest"
    type_guid: str      # "EF00" | "8200" | "8300" | "8E00" (LVM) | "FD00" (RAID)
    label: str | None

@dataclass(slots=True, frozen=True)
class Filesystem:
    device: str         # the partition this lands on, e.g. /dev/sda2
    kind: str           # "vfat" | "ext4" | "xfs" | "btrfs" | "f2fs" | "swap"
    label: str | None

@dataclass(slots=True, frozen=True)
class DiskPlan:
    disk: str                     # /dev/sda — the whole-disk target
    wipe: bool                    # zap existing GPT first
    partitions: list[Partition]
    filesystems: list[Filesystem]
```

The frontend renders current-vs-planned, the user confirms, and the core hands
the plan to the backend/executor as a unit. Applying it is a fixed ordered
pipeline the runner executes: **wipe → sgdisk partitions → settle (`udevadm
settle`/`partprobe`) → mkfs each → mkswap/swapon → generate fstab entries**.
The ordering (and the settle step, which trips up naive scripts) lives in one
place.

## Backend surface

Extend `org.gentoo.gest.Disk` (`interface.py` gains the names) with methods that
take the plan or its pieces:

| Method | Runs | Polkit action |
|---|---|---|
| `PartitionDisk(disk, wipe, a(isss))` | `wipefs` + `sgdisk` | `org.gentoo.gest.disk.partition` |
| `MakeFilesystem(device, kind, label)` | `mkfs.*` | `org.gentoo.gest.disk.mkfs` |
| `MakeSwap(device, label)` / `SwapOn`/`SwapOff` | `mkswap` / `swapon` | `org.gentoo.gest.disk.swap` |

Distinct polkit actions per destructive class (not one overloaded action) so an
installed-system policy can reason about them separately. On the **live CD** none
of this is consulted — `DirectExecutor` runs the same argv in-process because the
session is already root; the polkit actions matter only for the installed-system
path. Streaming and the busy lock come from the shared `runner.py`, so long
`mkfs` output streams through `runscreen.py` like emerge does.

## Module structure

The existing per-module convention extends in place — no new subsystem:

```
gest/core/disk/
  model.py           # + Partition, Filesystem, DiskPlan
  reader.py          # + partition-table read (sgdisk --print / blkid), fs detect
  commands.py        # + sgdisk/mkfs.*/mkswap/swapon/wipefs argv builders (pure)
  backend_client.py  # + obtains the Executor (see runtime-privilege-path) and
                     #   applies a DiskPlan; unchanged fstab/mount paths
  provision.py       # the apply pipeline (wipe→partition→settle→mkfs→swap→fstab)
```

`gest/tui/screens/disk.py` gains a partitioning view: pick a disk, build a plan
(or a "typical UEFI layout" template), review the diff, typed-confirm, watch the
streamed apply. fstab entries are generated from the plan's resulting UUIDs via
the existing fstab writer — so partitioning and fstab stay one module.

## Forward-compatibility with the installer

Per the roadmap's target-root constraint: `provision.py` operates on device
arguments, and the **fstab generation** step already resolves its output file
under a configurable root. So when the installer arrives, the same `DiskPlan`
applied on a live CD writes the target's `/mnt/gentoo/etc/fstab` instead of `/`,
with zero change to the partitioning/mkfs logic. `mkfs` a spare disk today and
`mkfs` the install target later are one code path.

## Testing

- **Live CD, real hardware:** the real test — boot the target box from a Gentoo
  minimal CD, GeST runs as root (`DirectExecutor`), partition/mkfs a scratch
  disk, verify with `lsblk`/`blkid` and a reboot.
- **Command builders:** pure argv tests for every `sgdisk`/`mkfs`/`mkswap` line.
- **Apply pipeline:** `FakeExecutor` (from runtime-privilege-path) records the
  ordered argv sequence for a given `DiskPlan` — asserts wipe precedes partition
  precedes settle precedes mkfs, without touching a disk.
- **Safety unit tests:** the validator refuses a mounted device, the running
  root, and the live medium; whole-disk wipe requires the typed token.

## Open questions

1. **Loop-device CI.** Can the safety validator be exercised in CI against a
   `losetup` backing file to test the *happy* path too, not just refusals?
   Proposed: yes for mkfs/mkswap on a loop device; partitioning stays live-CD-
   only.
2. **`parted` vs `sgdisk` for exotic layouts.** `sgdisk` covers GPT cleanly;
   revisit only if a case needs `parted`'s alignment/resize features.
3. **Alignment and `udev` settle.** Standardize on `sgdisk`'s default 1 MiB
   alignment and an explicit `udevadm settle` + `partprobe` after partitioning
   before mkfs — the most common source of "device busy" flakiness.
4. **Encryption ordering.** When LUKS lands, the plan grows a mapping layer
   (partition → luksFormat → open → mkfs on the mapped name); confirm the
   `DiskPlan` shape extends cleanly rather than needing a redesign.

## Non-goals

- LUKS/LVM/RAID in v1 (layered on later, same module).
- MBR/BIOS partitioning in v1 (GPT/UEFI first).
- The installer flow itself (this is a live-host provisioning module the
  installer will later orchestrate against a target root).
- Repartitioning/resize of in-use filesystems — GeST provisions; it does not do
  online resize.
