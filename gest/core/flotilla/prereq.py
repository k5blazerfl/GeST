"""The Gentoo prerequisites for a vessel — Flotilla's Gentoo-native edge.

Given a vessel's config, report exactly which packages / USE / services it needs.
Pure data (the atom table). *Applying* it — emerging, enabling ``libvirtd``,
adding the user to the ``libvirt`` group — routes through GeST's polkit'd
software/USE core, like every other module. See ``docs/design/flotilla.md`` §8.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gest.core.flotilla.model import (
    DISPLAY_NONE,
    FIRMWARE_UEFI,
    OS_WINDOWS,
    Vessel,
)


@dataclass(slots=True)
class Requirement:
    atom: str
    use: list[str] = field(default_factory=list)
    note: str = ""
    from_portage: bool = True  # False → fetched outside Portage (e.g. virtio-win)


# Enable + start these services, and add the user to these groups (the apply path
# does this via the software core; here we just report them).
SERVICES = ("libvirtd",)
GROUPS = ("libvirt", "kvm")


def requirements(vessel: Vessel) -> list[Requirement]:
    reqs = [
        Requirement("app-emulation/qemu", use=["spice", "usbredir", "virtfs"],
                    note="KVM accelerated QEMU (needs /dev/kvm + the kvm group)"),
        Requirement("app-emulation/libvirt",
                    note="the VM engine — enable+start libvirtd, join the libvirt group"),
    ]
    if vessel.firmware == FIRMWARE_UEFI:
        fw_note = "UEFI firmware" + (" + Secure Boot" if vessel.secureboot else "")
        reqs.append(Requirement("sys-firmware/edk2-ovmf", note=fw_note))
    if vessel.tpm:
        reqs.append(Requirement("app-crypt/swtpm", note="emulated TPM 2.0 (Windows 11)"))
    if vessel.shared_folders:
        reqs.append(Requirement("app-emulation/virtiofsd", note="virtiofs shared folders"))
    if vessel.display != DISPLAY_NONE:
        reqs.append(Requirement("app-emulation/virt-viewer",
                                note=f"{vessel.display.upper()} console client"))
    if vessel.os == OS_WINDOWS:
        reqs.append(Requirement("virtio-win", from_portage=False,
                                note="virtio driver ISO for Windows (fetched from Fedora)"))
    return reqs
