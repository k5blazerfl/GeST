"""The gestd module registry — one source of truth for what gestd exposes.

Each :class:`ModuleDescriptor` carries the display metadata a Control Center needs
to render and route to a module (title, category, freedesktop icon-name hint) plus
its D-Bus object path and interface. ``service`` iterates this to export the
objects, and the Catalog object serves it to clients, so the two can never drift.

Pure data (no dbus_next), so it is unit-testable and importable anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from gest.ipc.core_contract import (
    DISK_CORE_IFACE,
    DISK_CORE_PATH,
    FIREWALL_CORE_IFACE,
    FIREWALL_CORE_PATH,
    HOSTNAME_CORE_IFACE,
    HOSTNAME_CORE_PATH,
    LOCALIZATION_CORE_IFACE,
    LOCALIZATION_CORE_PATH,
    NETWORK_CORE_IFACE,
    NETWORK_CORE_PATH,
    SERVICES_CORE_IFACE,
    SERVICES_CORE_PATH,
    SOFTWARE_CORE_IFACE,
    SOFTWARE_CORE_PATH,
    SYSCTL_CORE_IFACE,
    SYSCTL_CORE_PATH,
    USERS_CORE_IFACE,
    USERS_CORE_PATH,
)


@dataclass(slots=True, frozen=True)
class ModuleDescriptor:
    id: str          # stable short id (matches the service factory key)
    title: str       # human label
    category: str    # Control Center grouping
    icon: str        # freedesktop icon-name hint
    path: str        # D-Bus object path
    iface: str       # D-Bus interface name


# The order here is the Control Center's default listing order. Categories follow
# the shared taxonomy both frontends render against:
#   System · Hardware · Network · Software · Services · Users & Security
# (Personalization is Qt/HeDE-only — a desktop-look category with no gestd module.)
MODULES: tuple[ModuleDescriptor, ...] = (
    ModuleDescriptor("hostname", "Hostname", "System",
                     "preferences-system", HOSTNAME_CORE_PATH, HOSTNAME_CORE_IFACE),
    ModuleDescriptor("localization", "Localization", "System",
                     "preferences-desktop-locale", LOCALIZATION_CORE_PATH, LOCALIZATION_CORE_IFACE),
    ModuleDescriptor("sysctl", "Kernel Parameters", "System",
                     "preferences-system", SYSCTL_CORE_PATH, SYSCTL_CORE_IFACE),
    ModuleDescriptor("disk", "Disks & Mounts", "Hardware",
                     "drive-harddisk", DISK_CORE_PATH, DISK_CORE_IFACE),
    ModuleDescriptor("network", "Network", "Network",
                     "network-workgroup", NETWORK_CORE_PATH, NETWORK_CORE_IFACE),
    ModuleDescriptor("software", "Software Management", "Software",
                     "system-software-install", SOFTWARE_CORE_PATH, SOFTWARE_CORE_IFACE),
    ModuleDescriptor("services", "Services (OpenRC)", "Services",
                     "applications-system", SERVICES_CORE_PATH, SERVICES_CORE_IFACE),
    ModuleDescriptor("users", "Users & Groups", "Users & Security",
                     "system-users", USERS_CORE_PATH, USERS_CORE_IFACE),
    ModuleDescriptor("firewall", "Firewall", "Users & Security",
                     "network-firewall", FIREWALL_CORE_PATH, FIREWALL_CORE_IFACE),
)
