"""The D-Bus + polkit contract shared by the GeST frontend and backend.

Keeping these names in one place means the unprivileged frontend, the root
service, and the installed system data files (D-Bus policy, polkit actions)
can never drift apart.
"""

# Well-known bus name claimed by the root service on the *system* bus.
BUS_NAME = "org.gentoo.gest"

# Object path + interface for the software-management (Portage) module.
SOFTWARE_PATH = "/org/gentoo/gest/Software"
SOFTWARE_IFACE = "org.gentoo.gest.Software"

# Object path + interface for the services (OpenRC/systemd) module.
SERVICES_PATH = "/org/gentoo/gest/Services"
SERVICES_IFACE = "org.gentoo.gest.Services"
SERVICES_POLKIT = "org.gentoo.gest.services.manage"

# Object path + interface for the users & groups module.
USERS_PATH = "/org/gentoo/gest/Users"
USERS_IFACE = "org.gentoo.gest.Users"
USERS_POLKIT = "org.gentoo.gest.users.manage"

# Object path + interface for the system-settings module.
SYSTEM_PATH = "/org/gentoo/gest/System"
SYSTEM_IFACE = "org.gentoo.gest.System"
SYSTEM_POLKIT = "org.gentoo.gest.system.configure"

# Object path + interface for the network module.
NETWORK_PATH = "/org/gentoo/gest/Network"
NETWORK_IFACE = "org.gentoo.gest.Network"
NETWORK_POLKIT = "org.gentoo.gest.network.manage"

# Object path + interface for the eselect module.
ESELECT_PATH = "/org/gentoo/gest/Eselect"
ESELECT_IFACE = "org.gentoo.gest.Eselect"
ESELECT_POLKIT = "org.gentoo.gest.eselect.manage"

# Object path + interface for the bootloader & kernel module.
BOOTLOADER_PATH = "/org/gentoo/gest/Bootloader"
BOOTLOADER_IFACE = "org.gentoo.gest.Bootloader"
BOOTLOADER_POLKIT = "org.gentoo.gest.bootloader.manage"
# Installing a bootloader (grub-install to the ESP/MBR) is more impactful than
# regenerating its config, so it gets its own action.
BOOTLOADER_INSTALL_POLKIT = "org.gentoo.gest.bootloader.install"

# Object path + interface for the repositories module (gated by the
# portage.configure polkit action; repository config is Portage config).
REPOS_PATH = "/org/gentoo/gest/Repos"
REPOS_IFACE = "org.gentoo.gest.Repos"

# Root SSH deploy-key helper for private git repositories. Reuses the
# portage.configure polkit action (it is repository sync setup).
SSH_PATH = "/org/gentoo/gest/Ssh"
SSH_IFACE = "org.gentoo.gest.Ssh"

# Object path + interface for the unified Portage-configuration module.
# One generic WriteConfig(a(ssu)) RPC applies files under /etc/portage/,
# gated by the single portage.configure polkit action.
PORTAGE_PATH = "/org/gentoo/gest/Portage"
PORTAGE_IFACE = "org.gentoo.gest.Portage"
PORTAGE_POLKIT = "org.gentoo.gest.portage.configure"

# Object path + interface for the disks & mounts module.
DISK_PATH = "/org/gentoo/gest/Disk"
DISK_IFACE = "org.gentoo.gest.Disk"
DISK_POLKIT = "org.gentoo.gest.disk.manage"
# Provisioning is split into distinct polkit actions per destructive class, so an
# installed-system policy can authorize (or refuse) partitioning, mkfs and swap
# independently rather than through one overloaded action.
DISK_PARTITION_POLKIT = "org.gentoo.gest.disk.partition"
DISK_MKFS_POLKIT = "org.gentoo.gest.disk.mkfs"
DISK_SWAP_POLKIT = "org.gentoo.gest.disk.swap"

# Object path + interface for the date & time module.
DATETIME_PATH = "/org/gentoo/gest/DateTime"
DATETIME_IFACE = "org.gentoo.gest.DateTime"
DATETIME_POLKIT = "org.gentoo.gest.datetime.manage"

# D-Bus error name the backend returns when a package operation is refused
# because another is already in progress (another GeST session, or an external
# emerge). The frontend maps it to a clean "busy" message instead of a raw crash.
BUSY_ERROR = "org.gentoo.gest.Busy"

# polkit action id prefix. Concrete actions append the verb, e.g.
# ``org.gentoo.gest.software.install``.
POLKIT_PREFIX = "org.gentoo.gest.software"


def polkit_action(verb: str) -> str:
    """Return the fully-qualified polkit action id for a software verb."""
    return f"{POLKIT_PREFIX}.{verb}"
