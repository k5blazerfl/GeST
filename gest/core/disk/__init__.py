"""Disks & mounts module core.

A view of the machine's block devices (`lsblk`) and its `/etc/fstab`, plus the
ability to mount/unmount fstab entries and add/edit/remove non-critical fstab
lines. Reading is unprivileged; mutations run through the polkit-gated backend.

Entries for the essential mount points (`/`, `/boot`, `/efi`, …) and swap are
treated as *protected*: shown read-only and refused by the backend, since a bad
/etc/fstab can leave a system unbootable. All fstab parsing, validation and
rendering lives here as pure, CI-testable functions in `fstab.py`; the backend
re-validates and does the privileged write.
"""
