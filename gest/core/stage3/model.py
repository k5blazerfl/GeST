"""Pure data for the stage3 module: the offered variants and a resolved selection.

``Stage3Variant`` is one entry in the pick-list the installer offers; a variant
plus a resolved mirror index becomes a ``Stage3Selection`` (concrete URLs, the
tarball filename, its byte size, and the derived ``.DIGESTS``/``.asc`` URLs).

**systemd** is the default: HeDE is systemd-only (greetd, logind/systemd D-Bus,
the seamless stack all assume it), so a GeSI install needs a systemd base. OpenRC
variants remain offered for a plain-Gentoo (non-HeDE) install.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_ARCH = "amd64"
ARM64_ARCH = "arm64"                 # Apple Silicon (Asahi) and other AArch64
SUPPORTED_ARCHES = (DEFAULT_ARCH, ARM64_ARCH)


@dataclass(slots=True, frozen=True)
class Stage3Variant:
    """One stage3 variant the installer can offer.

    ``flavor`` is the mirror's variant token (the ``<flavor>`` in
    ``latest-stage3-<flavor>.txt`` and ``stage3-<arch>-<flavor>-<stamp>``);
    ``label`` is the human description.
    """

    arch: str
    flavor: str
    label: str


# The offered variants; order is the pick-list order. Standard (systemd) is first
# and thus the default (DEFAULT_VARIANT) — the base a HeDE install needs. HeDE
# pulls its own Wayland desktop (gui-apps/hede), so the *Standard* systemd base is
# the right one, not desktop-systemd (which drags in an Xorg desktop profile). The
# OpenRC variants stay for a plain-Gentoo install.
VARIANTS: tuple[Stage3Variant, ...] = (
    Stage3Variant(DEFAULT_ARCH, "systemd", "Standard (systemd)"),
    Stage3Variant(DEFAULT_ARCH, "desktop-systemd", "Desktop (systemd)"),
    Stage3Variant(DEFAULT_ARCH, "openrc", "Standard (OpenRC)"),
    Stage3Variant(DEFAULT_ARCH, "desktop-openrc", "Desktop (OpenRC)"),
    Stage3Variant(DEFAULT_ARCH, "hardened-openrc", "Hardened (OpenRC)"),
    Stage3Variant(DEFAULT_ARCH, "nomultilib-openrc", "No-multilib (OpenRC)"),
)

# Apple Silicon (Asahi) groundwork: a stock arm64 stage3 is the base userland
# (systemd first, matching the amd64 default). The Asahi kernel (asahi-sources /
# overlay) and the m1n1 boot stub are a separate install increment; arch flows
# through the plan so the bootloader step emits arm64-efi GRUB. Not merged into the
# default offered VARIANTS yet.
ARM64_VARIANTS: tuple[Stage3Variant, ...] = (
    Stage3Variant(ARM64_ARCH, "systemd", "Standard (systemd, arm64)"),
    Stage3Variant(ARM64_ARCH, "openrc", "Standard (OpenRC, arm64)"),
    Stage3Variant(ARM64_ARCH, "desktop-openrc", "Desktop (OpenRC, arm64)"),
)

DEFAULT_VARIANT = VARIANTS[0]


def variants_for(arch: str) -> tuple[Stage3Variant, ...]:
    """The offered stage3 variants for a target ``arch`` (the installer's pick-list)."""
    return ARM64_VARIANTS if arch == ARM64_ARCH else VARIANTS


@dataclass(slots=True, frozen=True)
class Stage3Selection:
    """A fully-resolved stage3 download: everything the backend needs to fetch,
    verify and unpack one tarball.

    ``url`` is the tarball; ``digests_url``/``signature_url`` are the co-located
    ``.DIGESTS`` and ``.asc``; ``size`` is the byte size the index advertised (a
    sanity value, not the integrity check — that is the hash verification).
    """

    url: str
    filename: str
    size: int
    digests_url: str
    signature_url: str
