"""Disks & mounts module core.

A view of the machine's block devices (`lsblk`) and its `/etc/fstab`, plus the
ability to mount/unmount fstab entries and add/edit/remove non-critical fstab
lines. Reading is unprivileged; mutations run through the polkit-gated backend.

Entries for the essential mount points (`/`, `/boot`, `/efi`, …) and swap are
treated as *protected*: shown read-only and refused by the backend, since a bad
/etc/fstab can leave a system unbootable. All fstab parsing, validation and
rendering lives here as pure, CI-testable functions in `fstab.py`; the backend
re-validates and does the privileged write.

On the *provisioning* side the module also turns a disk into an install target:
`provision.py` partitions and makes filesystems, then `mount.py` mounts them
under a target root (`/mnt/gentoo`) and generates that system's own UUID-keyed
`/etc/fstab`. Those privileged operations are confined server-side to the
`/mnt`/`/media`/`/run/media` prefixes so they can never touch the running system.
"""
