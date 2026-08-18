"""Compile a :class:`~.model.Vessel` into a libvirt **domain XML** document.

Pure string/tree work (``xml.etree``) — unit-testable with no libvirt, the same
discipline as Gangway's ``commands.py`` and Drydock's launch pipeline. The host
backend (later) hands this to ``libvirtd`` to define the domain.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from gest.core.flotilla.model import (
    DISPLAY_NONE,
    DISPLAY_SPICE,
    FIRMWARE_UEFI,
    NET_BRIDGE,
    OS_WINDOWS,
    Vessel,
)

_DISK_LETTERS = "abcdefghijklmnop"
# Disks take letters a..j; the two CD-ROM slots (install + virtio) take k, l. Cap
# disks at 10 so they never collide with the CD-ROMs (or run off _DISK_LETTERS).
_MAX_DISKS = 10


def compile_domain(vessel: Vessel) -> str:
    domain = ET.Element("domain", type="kvm")
    ET.SubElement(domain, "name").text = vessel.id
    ET.SubElement(domain, "memory", unit="MiB").text = str(vessel.memory_mb)
    ET.SubElement(domain, "vcpu").text = str(vessel.vcpus)

    _os(domain, vessel)
    features = ET.SubElement(domain, "features")
    ET.SubElement(features, "acpi")
    ET.SubElement(features, "apic")
    if vessel.secureboot:
        ET.SubElement(features, "smm", state="on")  # required for OVMF Secure Boot
    ET.SubElement(domain, "cpu", mode="host-passthrough")
    ET.SubElement(domain, "clock",
                  offset="localtime" if vessel.os == OS_WINDOWS else "utc")

    _devices(domain, vessel)

    ET.indent(domain)
    return ET.tostring(domain, encoding="unicode")


def _os(domain: ET.Element, vessel: Vessel) -> None:
    os_el = ET.SubElement(domain, "os")
    if vessel.firmware == FIRMWARE_UEFI:
        os_el.set("firmware", "efi")  # libvirt auto-selects OVMF
    ET.SubElement(os_el, "type", arch="x86_64", machine="q35").text = "hvm"
    if vessel.install_iso:
        ET.SubElement(os_el, "boot", dev="cdrom")
    ET.SubElement(os_el, "boot", dev="hd")
    if vessel.firmware == FIRMWARE_UEFI and vessel.secureboot:
        fw = ET.SubElement(os_el, "firmware")
        ET.SubElement(fw, "feature", enabled="yes", name="secure-boot")


def _devices(domain: ET.Element, vessel: Vessel) -> None:
    devices = ET.SubElement(domain, "devices")

    if len(vessel.disks) > _MAX_DISKS:
        raise ValueError(
            f"vessel {vessel.id!r} has {len(vessel.disks)} disks; the domain XML "
            f"supports at most {_MAX_DISKS} (a..j; k, l are the CD-ROM slots)")

    for i, disk in enumerate(vessel.disks):
        d = ET.SubElement(devices, "disk", type="file", device="disk")
        ET.SubElement(d, "driver", name="qemu", type=disk.fmt)
        ET.SubElement(d, "source", file=disk.path)
        prefix = "vd" if disk.bus == "virtio" else "sd"
        ET.SubElement(d, "target", dev=prefix + _DISK_LETTERS[i], bus=disk.bus)

    for j, iso in enumerate(x for x in (vessel.install_iso, vessel.virtio_iso) if x):
        cd = ET.SubElement(devices, "disk", type="file", device="cdrom")
        ET.SubElement(cd, "driver", name="qemu", type="raw")
        ET.SubElement(cd, "source", file=iso)
        ET.SubElement(cd, "target", dev="sd" + _DISK_LETTERS[10 + j], bus="sata")
        ET.SubElement(cd, "readonly")

    for net in vessel.networks:
        if net.mode == NET_BRIDGE:
            iface = ET.SubElement(devices, "interface", type="bridge")
            ET.SubElement(iface, "source", bridge=net.source or "br0")
        else:  # nat / isolated → a libvirt network
            iface = ET.SubElement(devices, "interface", type="network")
            ET.SubElement(iface, "source", network=net.source or "default")
        ET.SubElement(iface, "model", type=net.model)

    if vessel.display != DISPLAY_NONE:
        graphics = ET.SubElement(devices, "graphics", type=vessel.display, autoport="yes")
        ET.SubElement(graphics, "listen", type="address")
        ET.SubElement(ET.SubElement(devices, "video"), "model", type="virtio")
    else:  # headless — a serial console instead
        ET.SubElement(ET.SubElement(devices, "serial", type="pty"), "target", port="0")
        ET.SubElement(ET.SubElement(devices, "console", type="pty"), "target",
                      type="serial", port="0")

    if vessel.guest_agent:
        ch = ET.SubElement(devices, "channel", type="unix")
        ET.SubElement(ch, "target", type="virtio", name="org.qemu.guest_agent.0")
    if vessel.display == DISPLAY_SPICE and vessel.spice_agent:
        ch = ET.SubElement(devices, "channel", type="spicevmc")
        ET.SubElement(ch, "target", type="virtio", name="com.redhat.spice.0")

    if vessel.tpm:
        tpm = ET.SubElement(devices, "tpm", model="tpm-crb")
        ET.SubElement(tpm, "backend", type="emulator", version="2.0")

    ET.SubElement(devices, "memballoon", model="virtio")

    for folder in vessel.shared_folders:
        fs = ET.SubElement(devices, "filesystem", type="mount", accessmode="passthrough")
        ET.SubElement(fs, "driver", type="virtiofs")
        ET.SubElement(fs, "source", dir=folder.path)
        ET.SubElement(fs, "target", dir=folder.tag)
