"""Privilege escalation (sudo / doas) in urwid: manage the wheel escalation rule.

Detects which tools are installed and shows the GeST-managed policy for each.
Applying goes through the polkit-gated PrivilegeBackend, which validates each
candidate with the tool's own checker (visudo -c / doas -C) before installing it.
The sudo drop-in lives in root-only /etc/sudoers.d, so its current state can't be
read unprivileged and is shown as "root-only".
"""

from __future__ import annotations

import contextlib

import urwid

from gest.core.privilege import reader, render
from gest.core.privilege.backend_client import PrivilegeBackend
from gest.core.privilege.model import EscalationPolicy
from gest.tui.runtime import App, Modal, Screen, boxed


def _fmt(policy: EscalationPolicy | None, unknown: str) -> str:
    if policy is None:
        return unknown
    mode = "passwordless" if policy.passwordless else (
        "password (persist)" if policy.persist else "password")
    return f"enabled — :{policy.group}, {mode}"


class PrivilegeScreen(Screen):
    def __init__(self, app: App) -> None:
        self._tools = reader.available_tools()
        self._info = urwid.Text("")
        body = urwid.Filler(boxed(self._info, title="Privilege escalation"), valign="top")
        super().__init__(
            app, body, title="Privilege (sudo / doas)",
            footer_keys=[("s", "Configure sudo"), ("d", "Configure doas"), ("Esc", "Back")],
        )
        self._render()

    def _render(self) -> None:
        has_sudo = "sudo" in self._tools
        has_doas = "doas" in self._tools
        sudo_state = (_fmt(reader.sudo_policy(), "unknown (root-only file)")
                      if has_sudo else "not installed")
        doas_state = _fmt(reader.doas_policy(), "not configured") if has_doas else "not installed"
        lines = [
            ("field", " sudo : "), f"{sudo_state}\n",
            ("field", " doas : "), f"{doas_state}\n",
            ("hint", "\n Grants a group (default wheel) privilege escalation. "
                     "sudo uses an\n isolated /etc/sudoers.d drop-in; doas uses a "
                     "managed block in\n /etc/doas.conf. Each change is validated "
                     "before it is applied."),
        ]
        if not self._tools:
            lines.append(("error", "\n\n Neither sudo nor doas is installed "
                                   "(emerge app-admin/sudo or app-admin/doas)."))
        self._info.set_text(lines)
        self.app.refresh()

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key in ("s", "S") and "sudo" in self._tools:
            self._configure("sudo")
            return None
        if key in ("d", "D") and "doas" in self._tools:
            self._configure("doas")
            return None
        return key

    def _configure(self, tool: str) -> None:
        current = reader.sudo_policy() if tool == "sudo" else reader.doas_policy()
        group = urwid.Edit("Group           : ", current.group if current else "wheel")
        enable = urwid.CheckBox("Enable escalation for this group",
                                state=current is not None)
        passwordless = urwid.CheckBox("Passwordless (no password prompt)",
                                      state=bool(current and current.passwordless))
        persist = urwid.CheckBox("Persist auth for a few minutes (doas)",
                                 state=bool(current.persist) if current else True)
        widgets = [
            urwid.Text(("hint", f"Configure {tool} wheel-style escalation.")),
            urwid.Divider(), group, urwid.Divider(), enable, passwordless,
        ]
        if tool == "doas":
            widgets.append(persist)

        def save():
            grp = group.edit_text.strip()
            if not render.valid_group(grp):
                self.app.notify("Invalid group name.", error=True)
                return
            self.app.pop()
            if tool == "sudo":
                self.app.run_async(self._call(
                    lambda b: b.set_sudo(grp, enable.state, passwordless.state)))
            else:
                self.app.run_async(self._call(
                    lambda b: b.set_doas(
                        grp, enable.state, passwordless.state, persist.state)))

        modal = Modal(self.app, f"Configure {tool}", widgets,
                      [("Apply", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 72), height=("relative", 62))

    async def _call(self, action) -> None:
        backend = PrivilegeBackend()
        try:
            await backend.connect()
            ok, out = await action(backend)
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            with contextlib.suppress(Exception):
                await backend.close()
            return
        with contextlib.suppress(Exception):
            await backend.close()
        self.app.notify(out or ("done" if ok else "failed"), error=not ok)
        if ok:
            self._render()
