"""The curated kernel config GeSI's genkernel build uses in the target.

genkernel's *default* config lacks common drivers — notably ``virtio`` — so a
system installed into a VM builds a kernel that can't find its own root disk
(``Could not find the root block device``). To fix that the installer ships a
curated, known-bootable config per arch (virtio + AHCI/SATA + NVMe + the common
filesystems) and points ``genkernel --kernel-config`` at it.

The config is shipped as package data but **staged** into the target at a fixed
path (rather than referenced in place), so the path genkernel sees is independent
of where — and under which Python — gest happens to be installed, in both the
live environment and the target chroot.

NOTE: ``config-amd64`` is currently a copy of
``packaging/livecd/amd64/kernel-config`` (the live image's proven config). Keep
them in sync until they're unified behind one canonical source.
"""

from __future__ import annotations

from importlib import resources

# Where the staged config lands in the target; genkernel reads this in-chroot.
TARGET_KERNEL_CONFIG = "/var/tmp/gest-kernel.config"

# arch → the package-data filename shipped for it.
_CONFIGS = {"amd64": "config-amd64"}


def bundled_config(arch: str) -> bytes | None:
    """The curated kernel-config bytes shipped for ``arch``, or ``None`` if the
    package ships none (then genkernel falls back to its own default config)."""
    name = _CONFIGS.get(arch)
    if name is None:
        return None
    res = resources.files("gest.core.kernel").joinpath(name)
    if not res.is_file():
        return None
    return res.read_bytes()
