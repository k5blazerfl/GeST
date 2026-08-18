"""Pure command builders for the libvirt host backend.

Flotilla drives libvirt through the ``virsh`` CLI (and ``virt-viewer`` for the
console, ``qemu-img`` for disks) — the same "build the argv, inject the runner"
pattern as Gangway's ``commands.py``. Everything here is a pure argv builder;
running them is the host-only edge (phase-2 CLI). No libvirt import.
"""

from __future__ import annotations

# libvirt connection URIs — session is rootless/per-user (the desktop default),
# system is the shared daemon (bridged networking, shared storage).
URI_SESSION = "qemu:///session"
URI_SYSTEM = "qemu:///system"
URIS = (URI_SESSION, URI_SYSTEM)


def virsh(uri: str, *args: str) -> list[str]:
    return ["virsh", "--connect", uri, *args]


def define_argv(uri: str, xml_path: str) -> list[str]:
    return virsh(uri, "define", xml_path)


def undefine_argv(uri: str, vessel_id: str, *, nvram: bool = True) -> list[str]:
    # --nvram removes the per-VM UEFI varstore too (UEFI/Secure Boot vessels).
    return virsh(uri, "undefine", vessel_id, *(["--nvram"] if nvram else []))


def start_argv(uri: str, vessel_id: str) -> list[str]:
    return virsh(uri, "start", vessel_id)


def shutdown_argv(uri: str, vessel_id: str) -> list[str]:
    return virsh(uri, "shutdown", vessel_id)  # graceful (ACPI)


def destroy_argv(uri: str, vessel_id: str) -> list[str]:
    return virsh(uri, "destroy", vessel_id)  # force off


def domstate_argv(uri: str, vessel_id: str) -> list[str]:
    return virsh(uri, "domstate", vessel_id)


def domifaddr_argv(uri: str, vessel_id: str) -> list[str]:
    # via the guest agent — the address the Gangway bridge will target (phase 4).
    return virsh(uri, "domifaddr", vessel_id, "--source", "agent")


def console_argv(uri: str, vessel_id: str) -> list[str]:
    """Open the SPICE/VNC console with virt-viewer (the traditional way to run
    any vessel, Windows included)."""
    return ["virt-viewer", "--connect", uri, vessel_id]


def alloc_disk_argv(path: str, size_gb: int, fmt: str = "qcow2") -> list[str]:
    return ["qemu-img", "create", "-f", fmt, path, f"{size_gb}G"]
