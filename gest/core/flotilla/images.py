"""Installable images — the turnkey new-vessel media catalog.

Linux distros and virtio-win are **direct-URL** images (fetched with ``curl``,
verified against a pinned SHA-256 when one is present). **Windows** media is
resolved by **mido** (the bash Windows-ISO fetcher) since Microsoft has no stable
unauthenticated URL. Pure data + argv builders; the download is a host op.

The catalog is a maintenance surface: URLs drift and checksums must be pinned per
release. Entries without a ``sha256`` fetch fine but skip verification (warned).
See ``docs/design/flotilla.md`` §10 (phase 3).
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

from gest.core.flotilla.model import OS_LINUX, OS_WINDOWS

FETCH_URL = "url"
FETCH_MIDO = "mido"


@dataclass(slots=True)
class Image:
    id: str
    os: str
    title: str
    url: str = ""            # direct download (fetcher == "url")
    sha256: str = ""         # pinned checksum; verified when non-empty
    fetcher: str = FETCH_URL  # "url" | "mido"
    edition: str = ""        # mido edition, e.g. "win11"
    filename: str = ""       # cached filename; derived from url/edition if empty


# NOTE: URLs point at current/stable artifacts and will need refreshing; SHA-256s
# are intentionally left unset here rather than shipped stale — pin them per
# release to turn on verification (fetch warns while they're empty).
CATALOG: list[Image] = [
    Image("debian", OS_LINUX, "Debian (netinst)",
          url="https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-12.7.0-amd64-netinst.iso"),
    Image("ubuntu", OS_LINUX, "Ubuntu Desktop LTS",
          url="https://releases.ubuntu.com/24.04/ubuntu-24.04.1-desktop-amd64.iso"),
    Image("fedora", OS_LINUX, "Fedora Workstation",
          url="https://download.fedoraproject.org/pub/fedora/linux/releases/40/Workstation/x86_64/iso/Fedora-Workstation-Live-x86_64-40-1.14.iso"),
    Image("arch", OS_LINUX, "Arch Linux",
          url="https://geo.mirror.pkgbuild.com/iso/latest/archlinux-x86_64.iso"),
    Image("virtio-win", OS_WINDOWS, "virtio-win drivers",
          url="https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso",
          filename="virtio-win.iso"),
    Image("win11", OS_WINDOWS, "Windows 11", fetcher=FETCH_MIDO, edition="win11"),
    Image("win10", OS_WINDOWS, "Windows 10", fetcher=FETCH_MIDO, edition="win10"),
]


def by_id(image_id: str) -> Image | None:
    return next((im for im in CATALOG if im.id == image_id), None)


def filename_for(image: Image) -> str:
    if image.filename:
        return image.filename
    if image.url:
        tail = image.url.rstrip("/").rsplit("/", 1)[-1]
        if tail:
            return tail
    return f"{image.edition or image.id}.iso"


def cached_path(image: Image, cache_base: str) -> str:
    return str(Path(cache_base).expanduser() / "images" / filename_for(image))


def curl_argv(url: str, dest: str) -> list[str]:
    return ["curl", "-fL", "--create-dirs", "-o", dest, url]


def mido_argv(edition: str, cache_dir: str) -> list[str]:
    """Run mido in the image cache so the Windows ISO lands there."""
    return ["sh", "-c", f"cd {shlex.quote(cache_dir)} && exec mido {shlex.quote(edition)}"]


def sha256_argv(path: str) -> list[str]:
    return ["sha256sum", path]


def unattend_iso_argv(staging_dir: str, out_iso: str, label: str) -> list[str]:
    """Build the small Windows guest-enablement provisioning ISO from a staging
    directory (autounattend.xml + firstboot.ps1). ``-V <label>`` sets the volume
    label firstboot locates itself by; ``-J -r`` add Joliet + Rock Ridge so the
    filenames survive. Requires ``dev-libs/libisoburn`` (xorriso)."""
    return ["xorriso", "-as", "mkisofs", "-V", label, "-J", "-r",
            "-o", out_iso, staging_dir]


def verify_sha256(sha256sum_output: str, expected: str) -> bool:
    """Compare ``sha256sum <file>`` output (``<hash>  <file>``) to ``expected``."""
    got = sha256sum_output.strip().split(maxsplit=1)[0] if sha256sum_output.strip() else ""
    return bool(expected) and got.lower() == expected.lower()
