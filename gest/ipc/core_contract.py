"""The `gestd` core-service D-Bus contract (Phase-0 scaffold; Hostname module).

Path-B for HeDE: a C++/Qt shell can't consume GeST's Python ``core`` in-process,
so ``core``'s *unprivileged* read/validate/render surface is promoted to a
D-Bus service — ``gestd`` — that any language can call. Writes stay on the
existing polkit-gated root backend (``gest/ipc/interface.py``); this file is the
*read side*.

Design decisions this scaffold pins down (see gest/coreservice/README.md):

* **Bus:** the user *session* bus. Reads are per-user and unprivileged, so gestd
  runs in the session like other desktop services (no polkit, no root).
* **Versioned:** the interface name carries the contract major version
  (``org.gentoo.gest.core1.*``). HeDE codes against ``core1``; a breaking change
  becomes ``core2`` and both can coexist, so GeST and HeDE evolve independently.
* **Per-module object:** one object path + interface per module, matching the
  Control Center's "modular and embeddable" requirement — each module is a gestd
  object plus a Qt/QML view on the HeDE side.
* **State as an extensible property bag:** ``GetState`` returns ``a{sv}`` (a
  variant map) rather than a fixed struct, so a module can gain fields without a
  breaking arity change. ``Validate`` returns ``(ok, message)``; ``Render``
  returns the exact config text the write would produce (a preview), keeping all
  parsing/validation/rendering logic in Python ``core`` — the C++ side never
  reimplements it.
"""

# Well-known name gestd claims on the SESSION bus.
CORE_BUS_NAME = "org.gentoo.gest.Core"

# Contract major version. Bump (and mint core2.* interfaces) on a breaking change.
CORE_API_VERSION = 1
_IFACE = f"org.gentoo.gest.core{CORE_API_VERSION}"

# --- Catalog (module enumeration) ------------------------------------------
# The top-level core object. A Control Center calls List() to discover every
# module without hardcoding it, then talks to each module's own object/interface.
#   List() -> aa{sv}   # per module: {id, title, category, icon, path, interface}
CATALOG_CORE_PATH = "/org/gentoo/gest/core"
CATALOG_CORE_IFACE = f"{_IFACE}.Catalog"

# --- Hostname module -------------------------------------------------------
# Interface surface (all unprivileged):
#   GetState()            -> state: a{sv}     # {"hostname": <s>}
#   Validate(name: s)     -> (ok: b, message: s)
#   Render(name: s)       -> text: s          # /etc/conf.d/hostname preview
# Applying a change is NOT here — that is a write, handled by the polkit root
# backend's System.SetHostname (gest/ipc/interface.py).
HOSTNAME_CORE_PATH = "/org/gentoo/gest/core/Hostname"
HOSTNAME_CORE_IFACE = f"{_IFACE}.Hostname"

# --- Software module (Portage-heavy reads; proves path B) ------------------
# Every package/detail is an extensible a{sv} property bag; list methods return
# aa{sv}. The C++ client never touches Portage — it gets structured data here.
#   ListInstalled()                                   -> aa{sv}  (whole list; small callers)
#   CountInstalled()                                  -> u       (snapshot total)
#   ListInstalledPage(offset:u, limit:u)              -> aa{sv}  (limit 0 = the rest)
#   RefreshInstalled()                                -> u       (drop snapshot, re-read, new total)
#   ListUpgradable()                                  -> aa{sv}
#   Search(term:s, fields:as, mode:s, ignore_case:b, limit:i) -> aa{sv}
#   PackagesInCategory(category:s, limit:i)           -> aa{sv}
#   ListCategories()                                  -> as
#   GetDetail(cp:s)                                   -> a{sv}   ({} if not found)
#   Counts()                                          -> a{sx}
# Installing/removing is a WRITE — the polkit root backend's Software interface.
# The installed list is paged: CountInstalled + ListInstalledPage read Portage once
# into a snapshot and slice it, so a lazy list scrolls without re-reading; a client
# calls RefreshInstalled to pick up installs/removes.
SOFTWARE_CORE_PATH = "/org/gentoo/gest/core/Software"
SOFTWARE_CORE_IFACE = f"{_IFACE}.Software"

# --- Services module (OpenRC) ----------------------------------------------
#   List()            -> aa{sv}   # {"name","status","runlevels":as,"enabled":b,"running":b}
#   Describe(name: s) -> a{sv}    # + description/needs/uses/wants/needed_by (as)
# Starting/stopping/enabling is a WRITE — the polkit root backend's Services iface.
SERVICES_CORE_PATH = "/org/gentoo/gest/core/Services"
SERVICES_CORE_IFACE = f"{_IFACE}.Services"

# --- Users & Groups module -------------------------------------------------
#   ListUsers()  -> aa{sv}  # {name, uid:x, gid:x, gecos, home, shell,
#                           #  full_name, system:b, groups:as}
#   ListGroups() -> aa{sv}  # {name, gid:x, members:as, system:b}
# Creating/modifying/deleting is a WRITE — the polkit root backend's Users iface.
USERS_CORE_PATH = "/org/gentoo/gest/core/Users"
USERS_CORE_IFACE = f"{_IFACE}.Users"

# --- Network module --------------------------------------------------------
#   ListInterfaces()   -> aa{sv}  # {name, state, mac, addresses:as, up:b, loopback:b}
#   GetConfig(iface:s) -> a{sv}   # netifrc: {iface, method, address, gateway}
# Bringing links up/down / writing netifrc is a WRITE — the polkit root backend.
NETWORK_CORE_PATH = "/org/gentoo/gest/core/Network"
NETWORK_CORE_IFACE = f"{_IFACE}.Network"

# --- Disks & mounts module -------------------------------------------------
#   List() -> aa{sv}   # block devices: {name, size, type, fstype, mountpoint}
DISK_CORE_PATH = "/org/gentoo/gest/core/Disk"
DISK_CORE_IFACE = f"{_IFACE}.Disk"

# --- Firewall module (nftables + firewalld, smart-detected) ----------------
#   Status()             -> a{sv}  # firewalld_installed/running, nftables_installed/active, active
#   GetNftPolicy()       -> a{sv}  # {managed:b, default_input, allow_ping:b, {tcp,udp}_ports:as}
#   GetFirewalldZone(z:s)-> a{sv}  # {zone, services:as, ports:as}
FIREWALL_CORE_PATH = "/org/gentoo/gest/core/Firewall"
FIREWALL_CORE_IFACE = f"{_IFACE}.Firewall"

# --- Localization module (timezone / locale / console keymap) --------------
#   GetState()               -> a{sv}  # {timezone, locale, keymap}
#   ListZones()/ListLocales()/ListKeymaps() -> as
#   Validate(field:s, value:s) -> (ok:b, message:s)   # field: timezone|locale|keymap
LOCALIZATION_CORE_PATH = "/org/gentoo/gest/core/Localization"
LOCALIZATION_CORE_IFACE = f"{_IFACE}.Localization"

# --- sysctl module ---------------------------------------------------------
#   GetSettings()          -> a{ss}   # the GeST sysctl.d drop-in key/values
#   Validate(a{ss})        -> (ok:b, message:s)
#   Render(a{ss})          -> s        # the drop-in text a write would produce
SYSCTL_CORE_PATH = "/org/gentoo/gest/core/Sysctl"
SYSCTL_CORE_IFACE = f"{_IFACE}.Sysctl"
