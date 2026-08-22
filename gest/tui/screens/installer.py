"""The Gentoo installer (urwid): a YaST-style settings overview that assembles an
InstallPlan, then a streamed run of the flow engine.

Reached only on the live-CD / root path (see the gated menu entry). The overview
edits an :class:`InstallSelections` in place; *Install* resolves the stage3, builds
the plan, and hands ``run_install`` to :class:`InstallRunScreen`. The engine does
the partitioning (step 1) and everything after — this screen only assembles and
drives; it never touches a disk itself.

5a wires the boot-critical rows (disk, stage3, kernel, bootloader, root password);
the system-config rows (hostname/timezone/locale/keymap, user, network) and the
live-network step land in 5b/5c.
"""

from __future__ import annotations

import contextlib

import urwid

from gest.core.disk import reader as disk_reader
from gest.core.exec.chroot import ChrootExecutor
from gest.core.exec.select import choose_executor
from gest.core.install import assemble
from gest.core.install.assemble import InstallSelections
from gest.core.install.context import InstallContext, StateStore
from gest.core.install.engine import run_install
from gest.core.install.netcheck import check_connectivity
from gest.core.install.plan import Phase
from gest.core.install.registry import build_registry
from gest.core.network import netifrc, resolv
from gest.core.stage3.model import VARIANTS
from gest.core.system import console as console_core
from gest.core.system import hostname as hostname_core
from gest.core.system import locale as locale_core
from gest.core.system import timezone as timezone_core
from gest.core.users.commands import valid_name as valid_user_name
from gest.tui.runtime import App, Modal, NavPile, Screen, boxed, strip_ansi
from gest.tui.screens.apply import _PROGRESS_RE, RawLogScreen, StreamLog
from gest.tui.screens.install.wizard import _GESI_LOGO_MARKUP, _GESI_LOGO_W


def _row(text) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


# Opt-in day-2 modules the installer can set up (keys match registry.TIER2_MODULES).
_TIER2_ORDER = ("sshd", "firewall", "sudo", "sysctl")
_TIER2_LABELS = {
    "sshd": "SSH server (sshd)",
    "firewall": "Firewall (nftables)",
    "sudo": "sudo for the wheel group",
    "sysctl": "sysctl hardening",
}


class InstallOverviewScreen(Screen):
    """The 'Installation Settings' overview — edit each setting, then Install."""

    def __init__(self, app: App, selections: InstallSelections | None = None) -> None:
        # The wizard's System Role gate hands in a role-proposed selection
        # (assemble.propose); with none we fall back to the bare defaults.
        self._sel = selections if selections is not None else InstallSelections()
        self._disks = [d for d in disk_reader.list_block_devices() if d.type == "disk"]
        self._walker = urwid.SimpleFocusListWalker([])
        self._list = urwid.ListBox(self._walker)
        self._pile = NavPile([boxed(self._list, title="Installation Settings")])
        super().__init__(
            app, self._pile, title="Install Gentoo",
            footer_keys=[("Enter", "Edit"), ("F10", "Install"), ("Esc", "Back")],
            help_text=(
                "Assemble a Gentoo install. Each row is a setting — Enter edits it,\n"
                "and F10 starts the install after a typed confirmation of the disk.\n\n"
                "The installer partitions the target, unpacks a stage3, and runs the\n"
                "Handbook steps against /mnt/gentoo. Everything here is a plan until\n"
                "you confirm — nothing touches a disk before then.\n\n"
                "Only the target disk and root password are required; the system,\n"
                "user and network rows carry sensible defaults you can edit."
            ),
        )
        self._online: bool | None = None      # None = not yet checked
        self._rows = [
            ("Connect this machine", self._connect_value, self._edit_connect),
            ("Target disk", self._disk_value, self._edit_disk),
            ("Stage3", lambda: self._sel.variant.label, self._edit_stage3),
            ("Hostname", lambda: self._sel.hostname, self._edit_hostname),
            ("Timezone", lambda: self._sel.timezone, self._edit_timezone),
            ("Locale", lambda: self._sel.locale, self._edit_locale),
            ("Console keymap", lambda: self._sel.keymap, self._edit_keymap),
            ("User account", self._user_value, self._edit_user),
            ("Network", self._network_value, self._edit_network),
            ("Day-2 setup", self._tier2_value, self._edit_tier2),
            ("Kernel", self._kernel_value, self._edit_kernel),
            ("Graphics", self._gpu_value, self._edit_gpu),
            ("Bootloader", self._bootloader_value, self._edit_bootloader),
            ("Root password", self._rootpw_value, self._edit_rootpw),
        ]
        self._render()
        app.run_async(self._check_online())

    # --- row value formatters ------------------------------------------------

    def _disk_value(self) -> str:
        if not self._sel.disk:
            return "— not selected —"
        swap = f"swap {self._sel.swap_size}" if self._sel.swap_size else "no swap"
        return (f"/dev/{self._sel.disk}  (ESP {self._sel.esp_size}, {swap}, "
                f"root {self._sel.root_fs})")

    def _kernel_value(self) -> str:
        jobs = "auto" if self._sel.kernel_jobs == 0 else str(self._sel.kernel_jobs)
        initrd = ", initramfs" if self._sel.kernel_initramfs else ""
        return f"{self._sel.kernel_method}  (-j {jobs}{initrd})"

    def _bootloader_value(self) -> str:
        if self._sel.firmware == "uefi":
            return f"GRUB / UEFI  (ESP {self._sel.efi_directory})"
        return f"GRUB / BIOS  (disk /dev/{self._sel.boot_disk or '?'})"

    def _rootpw_value(self) -> str:
        return "•••••• (set)" if self._sel.root_password else "— required —"

    def _gpu_value(self) -> str:
        if self._sel.gpu_auto:
            return "auto-detect (lspci)"
        if self._sel.nvidia_proprietary:
            return "NVIDIA proprietary" + (" (open modules)" if self._sel.kernel_open else "")
        if self._sel.video_cards:
            return " ".join(self._sel.video_cards)
        return "none (firmware only)"

    def _tier2_value(self) -> str:
        if not self._sel.tier2:
            return "(none)"
        return ", ".join(_TIER2_LABELS[k] for k in _TIER2_ORDER if k in self._sel.tier2)

    def _connect_value(self) -> str:
        if self._online is None:
            return "checking …"
        return "online" if self._online else "offline — connect before installing"

    def _row_attr(self, label: str, val: str) -> str:
        """The posture colour for a row's value."""
        if label == "Connect this machine":
            return "hint" if self._online is None else ("ok" if self._online else "error")
        if label in ("Target disk", "Root password"):
            return "error" if val.startswith("—") else "ok"
        return "ok"

    def _user_value(self) -> str:
        if not self._sel.create_user or not self._sel.user_name:
            return "(none)"
        extra = " · wheel (sudo)" if self._sel.user_wheel else ""
        return f"{self._sel.user_name}{extra}"

    def _network_value(self) -> str:
        if not self._sel.net_interface:
            return "(default)"
        how = "DHCP" if self._sel.net_dhcp else (self._sel.net_address or "static")
        dns = f", dns {' '.join(self._sel.net_nameservers)}" if self._sel.net_nameservers else ""
        return f"{self._sel.net_interface}  ({how}{dns})"

    def _render(self) -> None:
        rows = []
        for label, value, _edit in self._rows:
            val = value()
            marker = ("field", f" {label:<20}: ")
            attr = self._row_attr(label, val)
            rows.append(urwid.AttrMap(
                urwid.SelectableIcon([marker, (attr, val)], 0), None, focus_map="focus"))
        rows.append(urwid.Divider())
        rows.append(urwid.Text(("hint", " Enter edits the focused row · F10 installs")))
        self._walker[:] = rows
        self.app.refresh()

    # --- navigation ----------------------------------------------------------

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key in ("enter", "e"):
            idx = self._walker.focus
            if idx is not None and 0 <= idx < len(self._rows):
                self._rows[idx][2]()
            return None
        if key == "f10":
            self._install()
            return None
        return key

    # --- edit dialogs --------------------------------------------------------

    def _edit_disk(self) -> None:
        names = [d.name for d in self._disks]
        if not names:
            self.app.notify("No disks detected.", error=True)
            return
        pick = urwid.Edit("Disk (name)     : ", self._sel.disk or names[0])
        esp = urwid.Edit("ESP size        : ", self._sel.esp_size)
        swap = urwid.Edit("Swap (blank=none): ", self._sel.swap_size)
        rootfs = urwid.Edit("Root filesystem : ", self._sel.root_fs)

        def save():
            name = pick.edit_text.strip()
            if name not in names:
                self.app.notify(f"Unknown disk (have: {', '.join(names)}).", error=True)
                return
            self._sel.disk = name
            self._sel.esp_size = esp.edit_text.strip() or "512M"
            self._sel.swap_size = swap.edit_text.strip()
            self._sel.root_fs = rootfs.edit_text.strip() or "ext4"
            self.app.pop()
            self._render()

        avail = "Disks: " + ", ".join(f"{d.name} ({d.size})" for d in self._disks)
        modal = Modal(self.app, "Target disk & layout",
                      [urwid.Text(("hint", avail)),
                       urwid.Text(("error", " The whole disk is erased on install.")),
                       urwid.Divider(), pick, esp, swap, rootfs],
                      [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 74), height=("relative", 62))

    def _edit_stage3(self) -> None:
        walker = urwid.SimpleFocusListWalker([_row(v.label) for v in VARIANTS])
        with contextlib.suppress(ValueError):
            walker.set_focus(VARIANTS.index(self._sel.variant))

        def pick(_w=None):
            self._sel.variant = VARIANTS[walker.focus]
            self.app.pop()
            self._render()

        body = urwid.Pile([("pack", urwid.Text(("hint", "Highlight a variant, then Select.")),),
                           ("pack", urwid.Divider()),
                           ("weight", 1, urwid.BoxAdapter(urwid.ListBox(walker), 6))])
        modal = Modal(self.app, "Stage3 variant", [body],
                      [("Select", pick), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 60), height=("relative", 55))

    def _edit_hostname(self) -> None:
        edit = urwid.Edit("Hostname        : ", self._sel.hostname)

        def save():
            name = edit.edit_text.strip()
            if not hostname_core.valid_hostname(name):
                self.app.notify("Invalid hostname.", error=True)
                return
            self._sel.hostname = name
            self.app.pop()
            self._render()

        modal = Modal(self.app, "Hostname",
                      [urwid.Text(("hint", "The installed system's hostname.")),
                       urwid.Divider(), edit],
                      [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 60), height=("relative", 44))

    def _pick_modal(self, title: str, choices: list[str], current: str, apply) -> None:
        """A filterable picker modal (filter Edit + scrollable ListBox), modelled on
        ``system._ChoiceScreen`` — right for the ~hundreds of zones/locales/keymaps."""
        walker = urwid.SimpleFocusListWalker([])
        visible = list(choices)

        def fill(items):
            nonlocal visible
            visible = items
            walker[:] = [_row(c) for c in items] or [urwid.Text(" (no matches)")]
            if items and current in items:
                walker.set_focus(items.index(current))
            elif items:
                walker.set_focus(0)

        filt = urwid.Edit("Filter: ")

        def on_filter(_edit, text):
            needle = text.strip().lower()
            fill([c for c in choices if needle in c.lower()])

        urwid.connect_signal(filt, "change", on_filter)
        fill(choices)

        def select(_w=None):
            if visible and walker.focus is not None:
                apply(visible[walker.focus])
                self.app.pop()
                self._render()

        body = urwid.Pile([
            ("pack", urwid.Text(("hint", "Type to filter · ↓ into the list · Select."))),
            ("pack", filt),
            ("pack", urwid.Divider()),
            ("weight", 1, urwid.BoxAdapter(urwid.ListBox(walker), 10)),
        ])
        modal = Modal(self.app, title, [body], [("Select", select), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 62), height=("relative", 74))

    def _edit_timezone(self) -> None:
        def apply(value):
            self._sel.timezone = value

        self._pick_modal("Timezone", timezone_core.list_zones(), self._sel.timezone, apply)

    def _edit_locale(self) -> None:
        def apply(value):
            self._sel.locale = value

        self._pick_modal("Locale", locale_core.list_locales(), self._sel.locale, apply)

    def _edit_keymap(self) -> None:
        def apply(value):
            self._sel.keymap = value

        self._pick_modal("Console keymap", console_core.list_keymaps(), self._sel.keymap, apply)

    def _edit_user(self) -> None:
        create = urwid.CheckBox("Create a user", state=self._sel.create_user)
        name = urwid.Edit("Name            : ", self._sel.user_name)
        comment = urwid.Edit("Full name/comment: ", self._sel.user_comment)
        shell = urwid.Edit("Shell           : ", self._sel.user_shell)
        wheel = urwid.CheckBox("Add to wheel (sudo)", state=self._sel.user_wheel)

        def save():
            if not create.state:
                self._sel.create_user = False
                self.app.pop()
                self._render()
                return
            uname = name.edit_text.strip()
            if not valid_user_name(uname):
                self.app.notify("Invalid user name.", error=True)
                return
            self._sel.create_user = True
            self._sel.user_name = uname
            self._sel.user_comment = comment.edit_text.strip()
            self._sel.user_shell = shell.edit_text.strip() or "/bin/bash"
            self._sel.user_wheel = wheel.state
            self.app.pop()
            self._render()

        modal = Modal(self.app, "User account",
                      [urwid.Text(("hint", "An optional non-root user for the target.")),
                       urwid.Divider(), create, name, comment, shell, wheel],
                      [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 70), height=("relative", 60))

    def _edit_network(self) -> None:
        iface = urwid.Edit("Interface (blank=default): ", self._sel.net_interface)
        dhcp = urwid.CheckBox("Use DHCP", state=self._sel.net_dhcp)
        address = urwid.Edit("Static address (CIDR)   : ", self._sel.net_address)
        gateway = urwid.Edit("Gateway                 : ", self._sel.net_gateway)
        nameservers = urwid.Edit("Nameservers (space-sep) : ",
                                 " ".join(self._sel.net_nameservers))

        def save():
            name = iface.edit_text.strip()
            addr = address.edit_text.strip()
            gw = gateway.edit_text.strip()
            dns = tuple(nameservers.edit_text.split())
            if name and not dhcp.state:
                if not netifrc.valid_address(addr):
                    self.app.notify("Static address must be CIDR (e.g. 10.0.0.5/24).",
                                    error=True)
                    return
                if not netifrc.valid_gateway(gw):
                    self.app.notify("Invalid gateway address.", error=True)
                    return
            if name and not all(resolv.valid_nameserver(ns) for ns in dns):
                self.app.notify("Each nameserver must be a valid IP.", error=True)
                return
            self._sel.net_interface = name
            self._sel.net_dhcp = dhcp.state
            self._sel.net_address = addr
            self._sel.net_gateway = gw
            self._sel.net_nameservers = dns
            self.app.pop()
            self._render()

        modal = Modal(self.app, "Target network",
                      [urwid.Text(("hint", "The INSTALLED system's wired network. "
                                   "Blank interface leaves it default.")),
                       urwid.Text(("hint", "Static address/gateway apply when DHCP is off.")),
                       urwid.Divider(), iface, dhcp, address, gateway, nameservers],
                      [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 74), height=("relative", 64))

    def _edit_tier2(self) -> None:
        boxes = {k: urwid.CheckBox(_TIER2_LABELS[k], state=k in self._sel.tier2)
                 for k in _TIER2_ORDER}

        def save():
            self._sel.tier2 = {k for k, b in boxes.items() if b.state}
            self.app.pop()
            self._render()

        modal = Modal(
            self.app, "Day-2 setup (optional)",
            [urwid.Text(("hint", "Set these up during the install (config written, "
                                 "package emerged, service enabled at boot).")),
             urwid.Divider(), *boxes.values()],
            [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 64), height=("relative", 52))

    def _edit_kernel(self) -> None:
        method = urwid.Edit("Method (make/genkernel): ", self._sel.kernel_method)
        jobs = urwid.Edit("Jobs (0=auto)          : ", str(self._sel.kernel_jobs))
        initrd = urwid.CheckBox("Build an initramfs", state=self._sel.kernel_initramfs)

        def save():
            m = method.edit_text.strip()
            if m not in ("make", "genkernel"):
                self.app.notify("Method must be 'make' or 'genkernel'.", error=True)
                return
            j = jobs.edit_text.strip()
            if not j.isdigit():
                self.app.notify("Jobs must be a number (0 = auto).", error=True)
                return
            self._sel.kernel_method = m
            self._sel.kernel_jobs = int(j)
            self._sel.kernel_initramfs = initrd.state
            self.app.pop()
            self._render()

        modal = Modal(self.app, "Kernel build",
                      [urwid.Text(("hint", "make = configure+compile; genkernel = automated.")),
                       urwid.Divider(), method, jobs, initrd],
                      [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 68), height=("relative", 54))

    def _edit_gpu(self) -> None:
        # Modes map to (gpu_auto, video_cards, nvidia_proprietary). "Custom" reads the
        # tokens from the edit field; "Auto" re-enables lspci detection at install time.
        s = self._sel
        if s.gpu_auto:
            current = "auto"
        elif s.nvidia_proprietary:
            current = "nvidia"
        elif tuple(s.video_cards) == ("nouveau",):
            current = "nouveau"
        elif s.video_cards:
            current = "custom"
        else:
            current = "none"
        group: list = []
        modes = [
            ("auto", "Auto-detect (lspci) — recommended"),
            ("nvidia", "NVIDIA proprietary (nvidia-drivers + KMS)"),
            ("nouveau", "nouveau (open NVIDIA driver)"),
            ("custom", "Custom VIDEO_CARDS …"),
            ("none", "None (firmware only, no driver)"),
        ]
        buttons = {key: urwid.RadioButton(group, label, state=(key == current))
                   for key, label in modes}
        custom = urwid.Edit("VIDEO_CARDS: ", " ".join(s.video_cards) if current == "custom" else "")
        kopen = urwid.CheckBox("Open kernel modules — nvidia-drivers[kernel-open] "
                               "(Turing+/Ada)", state=s.kernel_open)

        def save():
            mode = next(k for k, b in buttons.items() if b.state)
            if mode == "auto":
                s.gpu_auto, s.video_cards, s.nvidia_proprietary = True, (), False
            elif mode == "nvidia":
                s.gpu_auto, s.video_cards, s.nvidia_proprietary = False, ("nvidia",), True
            elif mode == "nouveau":
                s.gpu_auto, s.video_cards, s.nvidia_proprietary = False, ("nouveau",), False
            elif mode == "custom":
                tokens = tuple(custom.edit_text.split())
                s.gpu_auto = False
                s.video_cards = tokens
                s.nvidia_proprietary = "nvidia" in tokens
            else:  # none
                s.gpu_auto, s.video_cards, s.nvidia_proprietary = False, (), False
            # kernel-open only applies to NVIDIA proprietary — assemble gates it.
            s.kernel_open = kopen.state
            self.app.pop()
            self._render()

        modal = Modal(self.app, "Graphics driver",
                      [urwid.Text(("hint", "Detected NVIDIA cards get the proprietary "
                                   "driver; every install gets firmware.")),
                       urwid.Divider(), *buttons.values(), urwid.Divider(), custom, kopen],
                      [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 70), height=("relative", 62))

    def _edit_bootloader(self) -> None:
        fw = urwid.Edit("Firmware (uefi/bios): ", self._sel.firmware)
        efi = urwid.Edit("ESP mount (uefi)    : ", self._sel.efi_directory)
        disk = urwid.Edit("Target disk (bios)  : ", self._sel.boot_disk)

        def save():
            f = fw.edit_text.strip()
            if f not in ("uefi", "bios"):
                self.app.notify("Firmware must be 'uefi' or 'bios'.", error=True)
                return
            self._sel.firmware = f
            self._sel.efi_directory = efi.edit_text.strip() or "/efi"
            self._sel.boot_disk = disk.edit_text.strip()
            self.app.pop()
            self._render()

        modal = Modal(self.app, "Bootloader (GRUB)",
                      [urwid.Text(("hint", "UEFI installs to the ESP; BIOS to a disk's MBR.")),
                       urwid.Divider(), fw, efi, disk],
                      [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 68), height=("relative", 54))

    def _edit_rootpw(self) -> None:
        pw1 = urwid.Edit("Password        : ", mask="*")
        pw2 = urwid.Edit("Confirm         : ", mask="*")

        def save():
            if pw1.edit_text != pw2.edit_text:
                self.app.notify("Passwords do not match.", error=True)
                return
            if not pw1.edit_text:
                self.app.notify("The root password can't be empty.", error=True)
                return
            self._sel.root_password = pw1.edit_text
            self.app.pop()
            self._render()

        modal = Modal(self.app, "Root password",
                      [urwid.Text(("hint", "Set the installed system's root password.")),
                       urwid.Divider(), pw1, pw2],
                      [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 60), height=("relative", 48))

    # --- live network --------------------------------------------------------

    async def _check_online(self) -> None:
        ok, _detail = await self.app.run_blocking(check_connectivity)
        self._online = ok
        self._render()

    async def _run_dhcpcd(self) -> None:
        self.app.notify("Bringing up wired network (dhcpcd) …")
        with contextlib.suppress(Exception):
            await choose_executor().run(["dhcpcd"])
        await self._check_online()

    def _edit_connect(self) -> None:
        def dhcp():
            self.app.pop()
            self.app.run_async(self._run_dhcpcd())

        def recheck():
            self.app.pop()
            self.app.run_async(self._check_online())

        modal = Modal(
            self.app, "Connect this machine",
            [urwid.Text("The install downloads a stage3 and emerges packages, so this "
                        "machine must be online."),
             urwid.Divider(),
             urwid.Text(("hint", "Wired usually comes up automatically. For Wi-Fi, use "
                                 "Network → Wi-Fi from the main menu, then Recheck here.")),
             urwid.Text(("hint", "This connects the LIVE machine — the installed "
                                 "system's network is the separate Network row."))],
            [("Bring up wired", dhcp), ("Recheck", recheck), ("Close", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 70), height=("relative", 50))

    # --- install -------------------------------------------------------------

    def _install(self) -> None:
        if not self._sel.disk:
            self.app.notify("Select a target disk first.", error=True)
            return
        if not self._sel.root_password:
            self.app.notify("Set a root password first.", error=True)
            return
        name = self._sel.disk
        entry = urwid.Edit(f"Type '{name}' to confirm erasing /dev/{name}: ")

        def go():
            if entry.edit_text.strip() != name:
                self.app.notify(f"Type '{name}' exactly to confirm.", error=True)
                return
            self.app.pop()
            self.app.push(InstallRunScreen(self.app, self._sel))

        modal = Modal(
            self.app, "Confirm install",
            [urwid.Text(("error", f" This ERASES /dev/{name} and installs Gentoo onto it.")),
             urwid.Divider(),
             urwid.Text("The disk is partitioned, a stage3 is unpacked, and the "
                        "Handbook steps run against /mnt/gentoo."),
             urwid.Divider(), entry],
            [("Erase & Install", go), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 72), height=("relative", 56))


# Braille spinner frames for the active-phase throb — plain terminal text, cycled
# on a set_alarm_in tick (same mechanism as the wizard's live clock). No graphics.
_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# The six install phases, Handbook-ordered, keyed by the Phase enum the registry
# stamps on every step. The branded overview shows one line per phase.
_PHASE_ORDER = [Phase.PREPARE_DISK, Phase.BASE_SYSTEM, Phase.CONFIGURE,
                Phase.KERNEL_BOOT, Phase.USERS_NETWORK, Phase.FINISH]
_PHASE_GLYPH = {"done": "✓", "failed": "✗", "pending": "·", "active": "▸"}
_PHASE_ATTR = {"done": "ok", "failed": "error", "pending": "dim", "active": "field"}

# Plain-language line for the active step (the raw emerge "(N of M)" detail
# overrides this while a package build is streaming). Default: the label itself.
_STEP_BLURB = {
    "Unpack the stage3 tarball": "unpacking the stage3 tarball",
    "Sync the Portage tree": "syncing the Portage tree",
    "Emerge @world": "emerging the base system — this is the long one",
    "Build the kernel": "building the kernel — this can take a while",
    "Install GPU drivers & firmware": "installing GPU drivers & firmware",
    "Install the HeDE desktop": "installing the HeDE desktop",
}


class InstallRunScreen(StreamLog, Screen):
    """Run the install behind a calm, branded overview: the GeST (GeSI) wordmark,
    the six phases with a live spinner on the one in flight, and a progress bar
    that creeps package-by-package during the long emerges. The full scrolling
    emerge output is one Tab away (and always spilled to an on-disk log)."""

    def __init__(self, app: App, sel: InstallSelections) -> None:
        self._sel = sel
        self._done = False
        # StreamLog: lazy on-disk log spill + coalesced redraws.
        self._logfile = None
        self._logpath: str | None = None
        self._refresh_pending = False
        # progress state
        self._labels: list[str] = []
        self._step_phases: list[Phase] = []
        self._step_index = 0
        self._total_steps = 1
        self._active_phase: Phase | None = None
        self._failed_phase: Phase | None = None
        self._spin = 0
        self._sub = ""                       # the active step's detail line

        # One bar + one phase-line object, shared by BOTH bodies (the old screen
        # rebuilt the bar after build_registry and left the stale one on screen).
        # 0..100 so it can creep smoothly within a step, not just per whole step.
        self._bar = urwid.ProgressBar("pb_normal", "pb_complete", 0, 100)
        self._phase = urwid.Text(("field", " Preparing …"))
        self._steps_text = urwid.Text("", wrap="clip")   # never wrap a long detail line
        self._log_walker = urwid.SimpleFocusListWalker([])
        self._log = urwid.ListBox(self._log_walker)

        self._brand_body = self._make_brand_body()
        self._detail_body = self._make_detail_body()
        self._branded = True
        super().__init__(app, self._brand_body, title="Installing Gentoo",
                         footer_keys=[("Tab", "Output log"), ("l", "View log"),
                                      ("Esc", "Back")])
        self._active_phase = Phase.PREPARE_DISK
        self._sub = "checking connectivity …"
        self._render_phases()
        self.app.main.set_alarm_in(0.12, self._tick)     # start the spinner
        app.run_async(self._run())

    # -- layout -------------------------------------------------------------

    def _make_brand_body(self) -> urwid.Widget:
        logo = urwid.Padding(urwid.Text(_GESI_LOGO_MARKUP, wrap="clip"),
                             align="center", width=_GESI_LOGO_W)
        panel = boxed(urwid.Pile([
            ("pack", urwid.Divider(" ")),
            ("pack", logo),
            ("pack", urwid.Divider(" ")),
            ("pack", urwid.Text(("dim", "Installing Gentoo…"), align="center")),
            ("pack", urwid.Divider(" ")),
            ("pack", self._steps_text),
            ("pack", urwid.Divider(" ")),
            ("pack", self._bar),
            ("pack", urwid.Divider(" ")),
            ("pack", urwid.Text(("dim", "Tab — full output log"), align="center")),
        ]), title="Installing Gentoo")
        return urwid.Filler(
            urwid.Padding(panel, align="center", width=("relative", 66),
                          min_width=_GESI_LOGO_W + 6),
            valign="middle", height="pack")

    def _make_detail_body(self) -> urwid.Widget:
        return urwid.Pile([
            ("pack", urwid.AttrMap(self._phase, "field")),
            ("pack", urwid.Divider("─")),
            ("pack", self._bar),
            ("pack", urwid.Divider("─")),
            ("weight", 1, boxed(self._log, title="Output")),
        ])

    def _toggle_view(self) -> None:
        self._branded = not self._branded
        self.set_body(self._brand_body if self._branded else self._detail_body)
        self.app.refresh()

    # -- progress rendering -------------------------------------------------

    def _phase_status(self, ph: Phase) -> str:
        if ph == self._failed_phase:
            return "failed"
        if self._failed_phase is not None:
            fi = _PHASE_ORDER.index(self._failed_phase)
            return "done" if _PHASE_ORDER.index(ph) < fi else "pending"
        if self._done:
            return "done"
        if self._active_phase is None:
            return "pending"
        ai, pi = _PHASE_ORDER.index(self._active_phase), _PHASE_ORDER.index(ph)
        return "done" if pi < ai else "active" if pi == ai else "pending"

    def _render_phases(self) -> None:
        spin = _SPINNER[self._spin % len(_SPINNER)]
        markup: list = []
        for ph in _PHASE_ORDER:
            status = self._phase_status(ph)
            markup.append((_PHASE_ATTR[status], f"   {_PHASE_GLYPH[status]}  {ph.value}\n"))
            if status == "active" and self._sub:
                markup.append(("dim", f"        {spin}  {self._sub}\n"))
        self._steps_text.set_text(markup)
        self._schedule_refresh()

    def _tick(self, *_) -> None:
        self._spin += 1
        self._render_phases()
        if not self._done and self in self.app._stack:
            self.app.main.set_alarm_in(0.12, self._tick)

    def _set_bar(self, sub_frac: float = 0.0) -> None:
        pct = (self._step_index + sub_frac) / max(self._total_steps, 1) * 100
        self._bar.set_completion(int(min(pct, 100)))

    def _on_step(self, index: int) -> None:
        self._step_index = index
        if 0 <= index < len(self._labels):
            label = self._labels[index]
            self._sub = _STEP_BLURB.get(label, label[:1].lower() + label[1:])
            self._phase.set_text(("field", f" {label}"))
            if index < len(self._step_phases):
                self._active_phase = self._step_phases[index]
        self._set_bar()
        self._render_phases()

    def _on_progress(self, lines) -> None:
        self._write_log(lines)                        # full on-disk record
        for ln in lines:
            self._log_walker.append(urwid.Text(strip_ansi(ln)))
            self._consume(ln)
        del self._log_walker[:-500]                   # cap the on-screen tail
        with contextlib.suppress(Exception):
            self._log_walker.set_focus(len(self._log_walker) - 1)
        self._schedule_refresh()

    def _consume(self, line: str) -> None:
        """Creep the bar within the active step from an emerge '(N of M)' marker."""
        m = _PROGRESS_RE.search(strip_ansi(line))
        if not m:
            return
        stage, n, total = m.group(1), int(m.group(2)), int(m.group(3))
        done = n if stage == "Installing" else max(n - 1, 0)
        self._set_bar(done / max(total, 1))
        # Keep the calm view short (the package atom is in the Tab output log).
        self._sub = f"{stage.lower()} {n} of {total} packages"

    async def _run(self) -> None:
        # Pre-flight: the install downloads a stage3 and emerges, so the live
        # machine must be online. Fail here with a clear message rather than deep
        # in the stage3 download.
        online, detail = await self.app.run_blocking(check_connectivity)
        self._on_progress([detail])
        if not online:
            self._finish(False, "No network connectivity — connect this machine "
                                "(the 'Connect this machine' row) and try again.")
            return

        # Resolve the stage3 (network) and assemble the plan.
        self._sub = "resolving the stage3 tarball …"
        self._render_phases()
        try:
            stage3 = await self.app.run_blocking(
                lambda: assemble.resolve_stage3(self._sel.variant))
            # Auto-detect the GPU (lspci) unless the user overrode it, so a detected
            # NVIDIA card gets the proprietary driver + a working Wayland/HeDE desktop
            # and every install gets firmware. Empty on a host with no detectable GPU.
            if self._sel.gpu_auto:
                detected = await self.app.run_blocking(assemble.resolve_gpu)
                self._sel.video_cards = detected.video_cards
                self._sel.nvidia_proprietary = detected.nvidia_proprietary
                self._sel.kernel_open = detected.kernel_open
                self._sel.nvidia_slot = detected.nvidia_slot
            plan = assemble.assemble_plan(self._sel, stage3)
        except Exception as exc:
            self._finish(False, f"Could not prepare the install: {exc}")
            return

        secret = self._sel.root_password
        user_secret = self._sel.user_password
        steps = build_registry(plan, root_secret=lambda: secret,
                               user_secret=lambda: user_secret)
        self._labels = [s.label for s in steps]
        self._step_phases = [s.phase for s in steps]
        self._total_steps = len(steps)

        host = choose_executor()
        root = self._sel.target_root
        ctx = InstallContext(
            root=root, host=host, target=ChrootExecutor(host, root),
            state=StateStore(root=root), plan=plan,
            devices=disk_reader.list_block_devices(),
            mounts=disk_reader.read_proc_mounts())

        try:
            await run_install(ctx, steps, on_progress=self._on_progress, on_step=self._on_step)
        except Exception as exc:
            self._finish(False, f"Install failed at: {getattr(exc, 'step', None) or exc}")
            return
        self._finish(True, f"Gentoo installed onto /dev/{self._sel.disk}.")

    def _finish(self, ok: bool, message: str) -> None:
        self._done = True                       # also stops the spinner tick
        self._close_log()
        if ok:
            self._bar.set_completion(100)
        else:
            self._failed_phase = self._active_phase
        self._phase.set_text(("ok" if ok else "error", " done" if ok else " failed"))
        self._render_phases()
        self.app.notify("done" if ok else "failed", error=not ok)
        if self._logpath and not ok:
            message = f"{message}\n\nFull log: {self._logpath}"

        def back():
            self.app.pop()      # modal
            self.app.pop()      # run screen → overview

        def reboot():
            self.app.pop()
            self.app.run_async(self._reboot())

        def view():
            self.app.pop()      # modal
            self.app.push(RawLogScreen(self.app, self._logpath))

        buttons = ([("Reboot now", reboot)] if ok else []) + [("Back", back)]
        if not ok and self._logpath:
            buttons.insert(0, ("View log", view))
        modal = Modal(
            self.app, "Installation complete" if ok else "Installation failed",
            [urwid.Text(("ok" if ok else "error", message)),
             urwid.Divider(),
             urwid.Text(("hint", "Remove the install media before rebooting."
                         if ok else "The target was left mounted for inspection."))],
            buttons)
        self.app.push_modal(modal, width=("relative", 66), height=("relative", 48))

    async def _reboot(self) -> None:
        with contextlib.suppress(Exception):
            await choose_executor().run(["reboot"])

    def handle_key(self, key):
        if key == "tab":
            self._toggle_view()
        elif key in ("l", "L"):
            self.app.push(RawLogScreen(self.app, self._logpath))
        elif key == "esc" and self._done:
            self.app.pop()
        else:
            return key
        return None
