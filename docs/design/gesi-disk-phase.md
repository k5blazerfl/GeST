# GeSI Disk Phase — overhaul plan (deferred, its own session)

Status: **planned, not built.** The wizard's Disk gate today does a *guided*
single-disk layout (ESP + RAM-sized swap + root, and an optional separate
`/home` — shipped). This document scopes the larger overhaul so it gets a
dedicated session and a tight plan rather than being bolted on.

## The ask (from the baremetal shakedown)
- An **Advanced** option that opens a **cfdisk-style partition editor** for RAID
  and other custom setups.

## The steer (important)
Make it **more than "being cfdisk."** Shelling out to `cfdisk` would give a raw
partition editor divorced from the installer's plan/proposal/review model. The
value of GeSI is the *reviewed plan* — the disk step must produce a `DiskPlan`
the Review gate can show (with `•changed`), validate, and apply atomically, not a
disk someone already re-partitioned by hand behind the installer's back.

## Why this is engine work, not just UI (see memory: gesi-disk-layout)
`DiskPlan` (gest/core/disk/model.py) is single-disk and flat: `disk, wipe,
partitions[], filesystems[]`. `plan_steps` does wipe → sgdisk → settle →
mkfs/mkswap only. `Partition.type_guid` can *name* LVM (8E00) / RAID (FD00) but
there is **no array builder and no plan_steps** for mdadm / pvcreate / vgcreate /
lvcreate / cryptsetup. So custom multi-device layouts need new core.

## Phasing (dependency order is load-bearing — real stacks nest RAID→LUKS→LVM→fs)
- **D-Adv0 — the editor** : a native (Qt/urwid) partition editor that edits a
  `DiskPlan` value (add/delete/resize/type/mountpoint), diffing against the
  guided proposal; still single-disk, still the existing apply engine. This is
  the "Advanced" entry point, and the seam everything below plugs into.
- **D2 — LUKS** : cryptsetup luksFormat/open in plan_steps; /etc/crypttab;
  initramfs `crypt`; GRUB cryptodisk. Passphrase is a run-time secret (like the
  root password), never in the frozen plan.
- **D3 — LVM** : pvcreate/vgcreate/lvcreate; mount/fstab over /dev/vg/lv;
  initramfs `lvm`. Composes on LUKS (LVM-on-LUKS) → after D2.
- **D4 — RAID (mdadm)** : the deep end — breaks the single-`disk` `DiskPlan` into
  a **multi-disk** model; mdadm create/assemble/settle; ESP replicated per
  member; GRUB on every member. Last, because it changes the model shape.

## Non-goals (v1)
Repair, nested-archive-of-disks, cloud/iSCSI targets. RAID write only via mdadm.

## Model design — SETTLED (2026-08-22): compose above `DiskPlan`, don't widen it

Decision: introduce a **`StoragePlan`** layer that *composes* the existing
single-disk `DiskPlan` (and its proven `plan_steps` engine) as the bottom
building block, rather than widening `DiskPlan.disk: str` into a multi-disk model.
Guided single-disk installs build a trivial `StoragePlan` (one `DiskPlan`, no
virtual devices) → **zero regression**; the Advanced editor edits a `StoragePlan`
value the Review gate can diff.

```
StoragePlan
  disks:       list[DiskPlan]      # partition each physical disk — TODAY's model + plan_steps, reused
  arrays:      list[RaidArray]     # mdadm: level, members[], name → /dev/mdN
  crypts:      list[LuksVolume]    # cryptsetup: backing dev → /dev/mapper/<name>; passphrase = RUNTIME secret
  volgroups:   list[VolumeGroup]   # pvcreate/vgcreate (+ logvols[]) → /dev/<vg>/<lv>
  filesystems: list[Filesystem]    # unchanged type — device is any str (partition | md | mapper | lv)
```

`storage_steps(plan)` = a **topological** builder over the virtual-device graph:
per-disk partitions (reuse `plan_steps`) → mdadm create/assemble → LUKS
luksFormat/luksOpen → LVM pvcreate/vgcreate/lvcreate → mkfs → mount. Real stacks
nest RAID→LUKS→LVM→fs, so build in that order.

### What already flexes (no change needed)
- `Filesystem.device` is a plain `str` → can point at `/dev/mdN`, `/dev/mapper/*`,
  `/dev/vg/lv`, not just a partition node.
- `Partition.type_guid` already names `8E00` (LVM) / `FD00` (RAID); nothing acts
  on it yet — the vocabulary exists.
- Mount-by-label (`_role_path`) already handles arbitrary roles; fstab keyed by UUID.

### The real gaps (the work)
1. **New step builders** (the bulk): mdadm, cryptsetup (+ `/etc/crypttab`), LVM
   (pvcreate/vgcreate/lvcreate). None exist today.
2. **`validate_plan`** — extend from one `plan.disk` to every disk in `disks[]`
   (each present, unmounted, not the boot medium) + composition consistency
   (referenced members exist, no cycles, ESP not on mdraid).
3. **Secrets** — LUKS passphrase rides the run-time `secret` callable pattern
   (like `SetRootPassword`), NEVER frozen in the plan.
4. **initramfs** — `BuildConfig` needs `lvm`/`mdadm`/`luks` flags derived from the
   StoragePlan → genkernel `--lvm --mdadm --luks` (kernel config already ships
   DM_CRYPT/RAID/LVM modules).
5. **bootloader** — GRUB `cryptodisk` + `GRUB_ENABLE_CRYPTODISK`; RAID means the
   ESP is replicated per member and GRUB installed on every member.
6. **`assemble.py`** — the single build site (`uefi_plan`/`bios_plan` +
   `derive_mount_plan`) wraps its result in a one-disk `StoragePlan`; the engine's
   Partition/Mount steps consume `storage_steps`.

### Blast radius (consumers of DiskPlan today)
`provision.py` (validate_plan/plan_steps/apply_plan/plan_phase_labels),
`mount.py` (derive_mount_plan/generate_target_fstab), `assemble.py` (one build
site), `registry.py` (Partition/MountTarget steps). Compose-above means these keep
working on the per-disk `DiskPlan` and gain a thin `StoragePlan` wrapper — not a
simultaneous rewrite.

## Reuse with GeST's admin Partitioner (design constraint)

GeST's Partitioner (`gest/tui/screens/partition.py :: PartitionScreen`, reached
via "Disks & Mounts") is **already** a second frontend over the same
`core/disk/provision` engine: it builds a `DiskPlan` (`uefi_plan`) and applies via
`apply_plan` (direct, live-root) **or** `apply_via_backend` (polkit, installed
system). So 3b's engine is shared by construction — the moment `StoragePlan` +
`storage_steps` + the mdadm/LUKS/LVM builders + multi-disk `validate_plan` land in
`core/disk/`, **both** the installer and the admin Partitioner gain RAID/LVM/LUKS.

**One deliberate choice to make it fully reusable:** build the D-Adv0 advanced
editor as a **standalone widget/screen that takes a `StoragePlan` and returns the
edited one** — NOT baked into the wizard. Then the installer's Advanced disk step
and `PartitionScreen` embed the same component; the admin Partitioner upgrades
from today's ESP+swap+root form to the full StoragePlan editor in lockstep.

**What does NOT transfer (context, not code):** live **non-destructive** edits of
*populated* disks — resize/move a partition with data, grow a live filesystem, add
a disk to a running array. The StoragePlan model is wipe-and-create; both surfaces
stop at that frontier today (the admin editor still works on spare/unmounted disks
via the backend). Non-destructive mutation is a separate, harder, later effort.

## Cross-refs
- Memory: `gesi-disk-layout` (the D1→D4 chart), `gesi-redesign-next` (the wizard).
- The guided single-disk layout + separate `/home` already ship in the Disk gate
  (gest/tui/screens/install/wizard.py :: DiskStep).
