"""Review — the wizard's terminus and single point of no return.

A phase-grouped, read-only readout of the assembled selection. It does not edit
in place: Enter on a fixable row *jumps back* to the wizard gate that owns it
(one edit path, no dual-editing). Derived values (stage3/profile/arch) are shown
greyed; blockers (no disk, missing root password or admin user, offline) are red
and disable Install until resolved. ``•changed`` marks a value the user moved off
the role's proposal. The typed disk-wipe confirmation lives only here.
"""

from __future__ import annotations

import urwid

from gest.core.install import assemble
from gest.core.install.assemble import InstallSelections
from gest.core.install.netcheck import check_connectivity
from gest.core.install.plan import sets_root_password
from gest.core.system.hostname import valid_hostname
from gest.core.users.commands import valid_name as valid_user_name
from gest.tui.runtime import App, Modal, NavPile, Screen, boxed, focusable_actions


def _sel_row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


class ReviewScreen(Screen):
    """Grouped readout with jump-back editing and the gated Install action."""

    def __init__(self, app: App, sel: InstallSelections) -> None:
        self.sel = sel
        self._online, _ = check_connectivity()
        self._walker = urwid.SimpleFocusListWalker([])
        self._list = urwid.ListBox(self._walker)
        # Back + Install are right-aligned action buttons at the bottom (GeST's
        # ActionRow convention); Install refuses while blockers remain, Back steps
        # to the previous gate.
        self._install_row = focusable_actions([("Back", app.pop), ("Install", self._install)])
        body = NavPile([("weight", 1, boxed(self._list, title="Review — Installation Settings")),
                        ("pack", self._install_row)])
        super().__init__(
            app, body,
            title="Install Gentoo — Review",
            footer_keys=[("Enter", "Edit setting"), ("Tab", "Install"), ("Esc", "Back")],
            help_text=(
                "A summary of everything the install will do. Enter on a setting\n"
                "jumps back to the gate that owns it; fix it there and Continue to\n"
                "return here. Greyed rows are derived and can't be edited. Red rows\n"
                "are blockers — Install stays disabled until they're resolved.\n\n"
                "Install asks you to type the disk name to confirm the wipe. Nothing\n"
                "touches a disk until then."))
        self.configure_pane_cycle(body, [0], action_row=self._install_row)
        self._build()

    # -- model ----------------------------------------------------------------
    def _proposed(self) -> InstallSelections:
        return assemble.propose(self.sel.role)

    def _changed(self, field: str) -> bool:
        return getattr(self.sel, field) != getattr(self._proposed(), field)

    def _blockers(self) -> list[str]:
        s = self.sel
        out = []
        if not s.disk:
            out.append("a target disk")
        if not self._online:
            out.append("a network connection")
        if sets_root_password(s.admin_model):
            if not s.root_password:
                out.append("a root password")
        elif not (s.create_user and valid_user_name(s.user_name) and s.user_wheel):
            out.append("an admin (wheel) user")
        if not valid_hostname(s.hostname):
            out.append("a valid hostname")
        return out

    def _groups(self):
        """(group_title, [(label, value, state, gate_key)]) — state: ok|derived|blocker."""
        s = self.sel
        chg = lambda f: " •changed" if self._changed(f) else ""  # noqa: E731
        disk_val = (f"/dev/{s.disk}" if s.disk else "(required)")
        layout = ("" if s.firmware == "bios" else f"ESP {s.esp_size} + ") + \
                 (f"swap {s.swap_size} + " if s.swap_size else "") + \
                 f"root ({s.root_fs})"
        build = "binary packages" if s.binary_pref else "compile from source"
        feats = ", ".join(sorted(s.capabilities)) or "(none)"
        user = s.user_name if s.create_user else "(none)"
        rootpw = "(set)" if s.root_password else "(not set)"
        online = "connected" if self._online else "NOT connected"
        return [
            ("Localization", [
                ("Timezone", s.timezone, "ok", "localization"),
                ("Locale", s.locale, "ok", "localization"),
                ("Keymap", s.keymap, "ok", "localization"),
                ("Clock", "chrony (NTP)" if s.clock == "chrony" else "local (no sync)",
                 "ok", "localization"),
            ]),
            ("Network (live)", [
                ("Connectivity", online, "ok" if self._online else "blocker", "online"),
            ]),
            ("System", [
                ("Role", s.role, "ok", "role"),
                ("Stage3", f"{s.variant.arch}/{s.variant.flavor}", "derived", None),
                ("Profile", assemble.profile_name(s.variant.arch, s.variant.flavor),
                 "derived", None),
                ("Desktop (HeDE)", "yes" if s.install_desktop else "no",
                 "ok", "role"),
            ]),
            ("Disk", [
                ("Target disk", disk_val, "ok" if s.disk else "blocker", "disk"),
                ("Layout", layout, "ok", "disk"),
            ]),
            ("Base System", [
                ("Build strategy", build + chg("binary_pref"), "ok", "base"),
                ("License", s.license + chg("license"), "ok", "base"),
                ("Features", feats + chg("capabilities"), "ok", "base"),
                ("Admin model", s.admin_model + chg("admin_model"), "ok", "base"),
            ]),
            ("Account", [
                ("Hostname", s.hostname,
                 "ok" if valid_hostname(s.hostname) else "blocker", "account"),
                ("User", user, "ok", "account"),
                ("Root password", rootpw,
                 "blocker" if (sets_root_password(s.admin_model)
                               and not s.root_password) else "ok", "account"),
            ]),
        ]

    # -- render + nav ---------------------------------------------------------
    def _build(self) -> None:
        prev = self._walker.get_focus()[1] if self._walker else None
        items: list[urwid.Widget] = []
        self._targets: list = []            # parallel: gate_key or "__install__" or None
        for title, rows in self._groups():
            items.append(urwid.Text(("pane_title", title)))
            self._targets.append(None)
            for label, value, state, gate in rows:
                attr = {"derived": "dim", "blocker": "error"}.get(state)
                suffix = "  (derived)" if state == "derived" else ""
                text = f"  {label:<16}: {value}{suffix}"
                if gate is None:
                    items.append(urwid.Text((attr, text) if attr else text))
                    self._targets.append(None)
                else:
                    w = _sel_row(text)
                    if attr:
                        w = urwid.AttrMap(urwid.SelectableIcon(text, 0), attr,
                                          focus_map="focus")
                    items.append(w)
                    self._targets.append(gate)
            items.append(urwid.Divider())
            self._targets.append(None)
        blockers = self._blockers()
        if blockers:
            items.append(urwid.Text(("error", " Blocked — still needs: "
                                     + ", ".join(blockers) + " (Install disabled)")))
            self._targets.append(None)
        self._walker[:] = items
        stops = self._stops()
        if stops:
            self._walker.set_focus(prev if prev in stops else stops[0])

    def _stops(self) -> list[int]:
        return [i for i, t in enumerate(self._targets) if t is not None]

    def handle_key(self, key):
        # Rebuild from the (possibly just-edited) selection so a jump-back's edits
        # show on return; cheap, and _build preserves the focus row.
        self._build()
        if key in ("f10", "f10 "):        # F10 installs from anywhere
            self._install()
            return None
        # The Install button (action row) is Tab-reached and fired by the base nav.
        if self._on_action_row():
            return key
        if key in ("up", "down"):
            stops = self._stops()
            if not stops:
                return None
            pos = self._walker.get_focus()[1]
            cur = stops.index(pos) if pos in stops else 0
            nxt = min(len(stops) - 1, cur + 1) if key == "down" else max(0, cur - 1)
            self._walker.set_focus(stops[nxt])
            return None
        if key == "enter":
            pos = self._walker.get_focus()[1]
            target = self._targets[pos] if 0 <= pos < len(self._targets) else None
            if target:
                self._jump(target)
            return None
        return key

    def _jump(self, gate_key: str) -> None:
        from gest.tui.screens.install.wizard import make_step
        self.app.push(make_step(
            gate_key, self.app, self.sel,
            return_to=lambda: make_step("review", self.app, self.sel)))

    def _install(self) -> None:
        blockers = self._blockers()
        if blockers:
            self.app.notify("Resolve blockers first: " + ", ".join(blockers), error=True)
            return
        name = self.sel.disk
        entry = urwid.Edit(f"Type '{name}' to confirm erasing /dev/{name}: ")

        def go():
            if entry.edit_text.strip() != name:
                self.app.notify(f"Type '{name}' exactly to confirm.", error=True)
                return
            self.app.pop()
            from gest.tui.screens.installer import InstallRunScreen
            self.app.push(InstallRunScreen(self.app, self.sel))

        modal = Modal(
            self.app, "Confirm install",
            [urwid.Text(("error", f"This ERASES /dev/{name} and installs Gentoo.")),
             urwid.Divider(), entry],
            [("Erase & install", go), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 66))
