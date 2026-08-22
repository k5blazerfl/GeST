"""The Flotilla vessel model — pure data + JSON (de)serialization.

A **vessel** is a managed libvirt domain + Flotilla config. It compiles to libvirt
domain XML (:mod:`.domainxml`) and drives the prerequisites table (:mod:`.prereq`).
Pure — no libvirt here. See ``docs/design/flotilla.md`` §4.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

OS_WINDOWS = "windows"
OS_LINUX = "linux"
OS_OTHER = "other"
OSES = (OS_WINDOWS, OS_LINUX, OS_OTHER)

FIRMWARE_UEFI = "uefi"
FIRMWARE_BIOS = "bios"
FIRMWARES = (FIRMWARE_UEFI, FIRMWARE_BIOS)

DISPLAY_SPICE = "spice"
DISPLAY_VNC = "vnc"
DISPLAY_NONE = "none"
DISPLAYS = (DISPLAY_SPICE, DISPLAY_VNC, DISPLAY_NONE)

# How a Windows vessel opens by default (both are always available). Non-Windows
# vessels always use the console.
ENTRY_CONSOLE = "console"
ENTRY_RDP = "rdp"
ENTRIES = (ENTRY_CONSOLE, ENTRY_RDP)

NET_NAT = "nat"
NET_BRIDGE = "bridge"
NET_ISOLATED = "isolated"
NET_MODES = (NET_NAT, NET_BRIDGE, NET_ISOLATED)

CONFIG_VERSION = 1


@dataclass(slots=True)
class Disk:
    path: str
    size_gb: int = 40
    fmt: str = "qcow2"
    bus: str = "virtio"
    boot: bool = True

    def to_dict(self) -> dict:
        return {"path": self.path, "size_gb": self.size_gb, "fmt": self.fmt,
                "bus": self.bus, "boot": self.boot}

    @classmethod
    def from_dict(cls, d: Mapping) -> Disk:
        return cls(path=str(d["path"]), size_gb=int(d.get("size_gb", 40)),
                   fmt=str(d.get("fmt", "qcow2")), bus=str(d.get("bus", "virtio")),
                   boot=bool(d.get("boot", True)))


@dataclass(slots=True)
class Network:
    mode: str = NET_NAT
    model: str = "virtio"
    source: str = ""  # bridge name (bridge) or network name (nat/isolated)

    def to_dict(self) -> dict:
        return {"mode": self.mode, "model": self.model, "source": self.source}

    @classmethod
    def from_dict(cls, d: Mapping) -> Network:
        return cls(mode=str(d.get("mode", NET_NAT)), model=str(d.get("model", "virtio")),
                   source=str(d.get("source", "")))


@dataclass(slots=True)
class SharedFolder:
    tag: str
    path: str  # host path exported over virtiofs (Linux guests)

    def to_dict(self) -> dict:
        return {"tag": self.tag, "path": self.path}

    @classmethod
    def from_dict(cls, d: Mapping) -> SharedFolder:
        return cls(tag=str(d["tag"]), path=str(d["path"]))


# TSAppAllowList\Applications\<key>\CommandLineSetting (DWORD): 0 = no command
# line allowed, 1 = any command line, 2 = only a fixed command line. Default 1.
CMDLINE_ANY = 1


@dataclass(slots=True)
class RemoteAppProgram:
    """A published RemoteApp on a Windows vessel — one TSAppAllowList entry the
    guest firstboot writes, and (later) a FreeRDP RAIL alias Gangway launches by.
    ``key`` is the ``Applications\\<key>`` subkey / RAIL alias; ``path`` is the
    guest-side Windows path to the executable; ``vpath`` is its expandable form."""
    key: str
    name: str
    path: str
    vpath: str = ""  # env-var form (e.g. %ProgramFiles%\…); defaults to path
    cmdline_setting: int = CMDLINE_ANY

    def to_dict(self) -> dict:
        return {"key": self.key, "name": self.name, "path": self.path,
                "vpath": self.vpath, "cmdline_setting": self.cmdline_setting}

    @classmethod
    def from_dict(cls, d: Mapping) -> RemoteAppProgram:
        return cls(key=str(d["key"]), name=str(d.get("name", "")), path=str(d["path"]),
                   vpath=str(d.get("vpath", "")),
                   cmdline_setting=int(d.get("cmdline_setting", CMDLINE_ANY)))


@dataclass(slots=True)
class Vessel:
    id: str
    name: str
    os: str = OS_LINUX
    firmware: str = FIRMWARE_UEFI
    secureboot: bool = False
    tpm: bool = False
    vcpus: int = 2
    memory_mb: int = 4096
    disks: list[Disk] = field(default_factory=list)
    install_iso: str = ""
    virtio_iso: str = ""  # virtio-win, attached at install for Windows guests
    networks: list[Network] = field(default_factory=lambda: [Network()])
    display: str = DISPLAY_SPICE
    spice_agent: bool = True
    entry: str = ENTRY_CONSOLE  # Windows: console (default) | rdp
    guest_agent: bool = True
    shared_folders: list[SharedFolder] = field(default_factory=list)
    gangway_profile: str = ""  # linked Gangway profile id (Windows, seamless RDP)
    # Guest-enablement (Windows RemoteApp provisioning, §5/phase-5). Opt-in — empty
    # by default. `provisioned` records that the unattend ISO was built for these.
    remote_app_programs: list[RemoteAppProgram] = field(default_factory=list)
    unattend_iso: str = ""  # provisioning CD (autounattend + firstboot), attached at install
    unattend_username: str = ""  # the local account Gangway authenticates as
    provisioned: bool = False

    def is_valid(self) -> bool:
        return (bool(self.id) and self.os in OSES and self.firmware in FIRMWARES
                and self.display in DISPLAYS and self.entry in ENTRIES
                and self.vcpus > 0 and self.memory_mb > 0)

    def to_dict(self) -> dict:
        return {
            "version": CONFIG_VERSION, "id": self.id, "name": self.name, "os": self.os,
            "firmware": self.firmware, "secureboot": self.secureboot, "tpm": self.tpm,
            "vcpus": self.vcpus, "memory_mb": self.memory_mb,
            "disks": [d.to_dict() for d in self.disks],
            "install_iso": self.install_iso, "virtio_iso": self.virtio_iso,
            "networks": [n.to_dict() for n in self.networks],
            "display": self.display, "spice_agent": self.spice_agent, "entry": self.entry,
            "guest_agent": self.guest_agent,
            "shared_folders": [s.to_dict() for s in self.shared_folders],
            "gangway_profile": self.gangway_profile,
            "remote_app_programs": [p.to_dict() for p in self.remote_app_programs],
            "unattend_iso": self.unattend_iso, "unattend_username": self.unattend_username,
            "provisioned": self.provisioned,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> Vessel:
        return cls(
            id=str(d["id"]), name=str(d.get("name", "")), os=str(d.get("os", OS_LINUX)),
            firmware=str(d.get("firmware", FIRMWARE_UEFI)),
            secureboot=bool(d.get("secureboot", False)), tpm=bool(d.get("tpm", False)),
            vcpus=int(d.get("vcpus", 2)), memory_mb=int(d.get("memory_mb", 4096)),
            disks=[Disk.from_dict(x) for x in d.get("disks", [])],
            install_iso=str(d.get("install_iso", "")), virtio_iso=str(d.get("virtio_iso", "")),
            networks=[Network.from_dict(x) for x in d.get("networks", [])] or [Network()],
            display=str(d.get("display", DISPLAY_SPICE)),
            spice_agent=bool(d.get("spice_agent", True)),
            entry=str(d.get("entry", ENTRY_CONSOLE)),
            guest_agent=bool(d.get("guest_agent", True)),
            shared_folders=[SharedFolder.from_dict(x) for x in d.get("shared_folders", [])],
            gangway_profile=str(d.get("gangway_profile", "")),
            remote_app_programs=[RemoteAppProgram.from_dict(x)
                                 for x in d.get("remote_app_programs", [])],
            unattend_iso=str(d.get("unattend_iso", "")),
            unattend_username=str(d.get("unattend_username", "")),
            provisioned=bool(d.get("provisioned", False)),
        )


def recommended(os: str, name: str, vessel_id: str) -> Vessel:
    """A vessel with OS-appropriate defaults — Windows gets UEFI + Secure Boot +
    TPM 2.0 (Win11) and the RDP-capable entry left as console until linked; Linux
    gets a plain UEFI guest."""
    windows = os == OS_WINDOWS
    return Vessel(
        id=vessel_id, name=name, os=os,
        firmware=FIRMWARE_UEFI, secureboot=windows, tpm=windows,
        memory_mb=8192 if windows else 4096,
    )
