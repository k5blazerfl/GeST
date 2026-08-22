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

## Cross-refs
- Memory: `gesi-disk-layout` (the D1→D4 chart), `gesi-redesign-next` (the wizard).
- The guided single-disk layout + separate `/home` already ship in the Disk gate
  (gest/tui/screens/install/wizard.py :: DiskStep).
