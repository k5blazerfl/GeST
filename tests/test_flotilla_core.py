"""CI-safe tests for the Flotilla pure core: vessel model, domain-XML compiler,
prereq table. No libvirt is touched."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from gest.core.flotilla import prereq
from gest.core.flotilla.domainxml import compile_domain
from gest.core.flotilla.model import (
    OS_LINUX,
    OS_WINDOWS,
    Disk,
    Network,
    SharedFolder,
    Vessel,
    recommended,
)


def _win(**over) -> Vessel:
    base = dict(id="win11", name="Windows 11", os=OS_WINDOWS, firmware="uefi",
                secureboot=True, tpm=True, vcpus=4, memory_mb=8192,
                disks=[Disk(path="/vm/win11.qcow2", size_gb=64)],
                install_iso="/iso/win11.iso", virtio_iso="/iso/virtio-win.iso")
    base.update(over)
    return Vessel(**base)


# ---- model -------------------------------------------------------------
def test_vessel_round_trip():
    v = _win(shared_folders=[SharedFolder(tag="host", path="/srv/share")],
             gangway_profile="win11-rdp")
    assert Vessel.from_dict(v.to_dict()) == v


def test_is_valid():
    assert _win().is_valid()
    assert not Vessel(id="", name="x").is_valid()
    assert not Vessel(id="x", name="x", os="beos").is_valid()
    assert not Vessel(id="x", name="x", vcpus=0).is_valid()
    assert not Vessel(id="x", name="x", entry="carrier-pigeon").is_valid()


def test_recommended_windows_gets_uefi_sb_tpm():
    v = recommended(OS_WINDOWS, "Win 11", "win11")
    assert v.firmware == "uefi" and v.secureboot and v.tpm and v.memory_mb == 8192
    assert v.entry == "console"  # RDP is opt-in, not the default
    lin = recommended(OS_LINUX, "Debian", "debian")
    assert not lin.secureboot and not lin.tpm


def test_from_dict_defaults_a_network():
    v = Vessel.from_dict({"id": "x", "name": "x"})  # no networks key
    assert len(v.networks) == 1 and v.networks[0].mode == "nat"


# ---- domain XML --------------------------------------------------------
def _dom(vessel) -> ET.Element:
    return ET.fromstring(compile_domain(vessel))


def test_domain_basics():
    root = _dom(_win())
    assert root.tag == "domain" and root.get("type") == "kvm"
    assert root.findtext("name") == "win11"
    assert root.findtext("memory") == "8192"
    assert root.findtext("vcpu") == "4"


def test_windows_uefi_secureboot_tpm():
    root = _dom(_win())
    assert root.find("os").get("firmware") == "efi"
    assert root.find("os/firmware/feature").get("name") == "secure-boot"
    assert root.find("features/smm") is not None  # SMM required for Secure Boot
    assert root.find("devices/tpm/backend").get("version") == "2.0"
    assert root.find("clock").get("offset") == "localtime"  # Windows


def test_linux_defaults_utc_no_tpm():
    root = _dom(Vessel(id="deb", name="Debian", os=OS_LINUX, tpm=False, secureboot=False,
                       disks=[Disk(path="/vm/deb.qcow2")]))
    assert root.find("clock").get("offset") == "utc"
    assert root.find("devices/tpm") is None
    assert root.find("features/smm") is None


def test_disks_and_install_media():
    root = _dom(_win())
    disks = root.findall("devices/disk[@device='disk']")
    assert disks[0].find("target").get("dev") == "vda"
    assert disks[0].find("target").get("bus") == "virtio"
    cdroms = root.findall("devices/disk[@device='cdrom']")
    sources = {c.find("source").get("file") for c in cdroms}
    assert sources == {"/iso/win11.iso", "/iso/virtio-win.iso"}  # install + virtio-win
    assert root.find("os/boot").get("dev") == "cdrom"  # boots the installer first


def test_networks_nat_and_bridge():
    v = _win(networks=[Network(mode="nat"), Network(mode="bridge", source="br0")])
    ifaces = _dom(v).findall("devices/interface")
    assert ifaces[0].get("type") == "network"
    assert ifaces[0].find("source").get("network") == "default"
    assert ifaces[1].get("type") == "bridge"
    assert ifaces[1].find("source").get("bridge") == "br0"


def test_spice_display_and_agents():
    root = _dom(_win(display="spice", spice_agent=True, guest_agent=True))
    assert root.find("devices/graphics").get("type") == "spice"
    channels = {c.find("target").get("name") for c in root.findall("devices/channel")}
    assert "org.qemu.guest_agent.0" in channels
    assert "com.redhat.spice.0" in channels


def test_headless_has_serial_no_graphics():
    root = _dom(_win(display="none"))
    assert root.find("devices/graphics") is None
    assert root.find("devices/serial") is not None


def test_virtiofs_shared_folder():
    root = _dom(_win(shared_folders=[SharedFolder(tag="host", path="/srv/share")]))
    fs = root.find("devices/filesystem")
    assert fs.find("driver").get("type") == "virtiofs"
    assert fs.find("source").get("dir") == "/srv/share"
    assert fs.find("target").get("dir") == "host"


# ---- prereqs -----------------------------------------------------------
def test_prereqs_windows_uefi_tpm():
    atoms = [r.atom for r in prereq.requirements(_win())]
    assert "app-emulation/qemu" in atoms and "app-emulation/libvirt" in atoms
    assert "sys-firmware/edk2-ovmf" in atoms  # UEFI
    assert "app-crypt/swtpm" in atoms  # TPM
    assert "virtio-win" in atoms
    virtio = next(r for r in prereq.requirements(_win()) if r.atom == "virtio-win")
    assert virtio.from_portage is False  # fetched from Fedora


def test_prereqs_linux_minimal():
    v = Vessel(id="deb", name="Debian", os=OS_LINUX, firmware="bios", tpm=False)
    atoms = [r.atom for r in prereq.requirements(v)]
    assert "sys-firmware/edk2-ovmf" not in atoms  # bios
    assert "app-crypt/swtpm" not in atoms  # no tpm
    assert "virtio-win" not in atoms  # linux
    assert prereq.SERVICES == ("libvirtd",) and "libvirt" in prereq.GROUPS
