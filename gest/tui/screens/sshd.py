"""SSH server config in urwid: edit the managed sshd_config directives.

Reads current settings unprivileged; applying goes through the polkit-gated
SshdBackend, which validates the candidate with `sshd -t` before replacing the
live file and reloading the daemon.
"""

from __future__ import annotations

import contextlib
from dataclasses import replace

import urwid

from gest.core.sshd import reader
from gest.core.sshd.backend_client import SshdBackend
from gest.core.sshd.config import valid_port
from gest.core.sshd.model import ROOT_LOGIN_VALUES
from gest.tui.runtime import App, Modal, Screen, boxed


def _yn(value: bool) -> str:
    return "yes" if value else "no"


def _mark(text: str, good: bool, *, risky: bool = False):
    """Colour a directive value by its security posture: red when it weakens the
    server, green when it hardens it, plain when it's neutral/common."""
    if risky:
        return ("error", text)
    if good:
        return ("ok", text)
    return text


class SshdScreen(Screen):
    def __init__(self, app: App) -> None:
        self._settings = reader.current_settings()
        self._info = urwid.Text("")
        body = urwid.Filler(boxed(self._info, title="sshd_config"), valign="top")
        super().__init__(
            app, body, title="SSH Server (sshd)",
            footer_keys=[
                ("o", "Port"), ("r", "Root login"), ("a", "Password auth"),
                ("k", "Pubkey auth"), ("x", "X11"), ("e", "Empty pw"),
                ("F10", "Apply"), ("Esc", "Back"),
            ],
            help_text=(
                "Manage the security-relevant sshd_config directives; every\n"
                "other line in the file is preserved, and changes are checked\n"
                "with sshd -t before they are applied.\n\n"
                "o   set the listen port\n"
                "r   cycle PermitRootLogin (no / prohibit-password /\n"
                "    forced-commands-only / yes)\n"
                "a   toggle PasswordAuthentication\n"
                "k   toggle PubkeyAuthentication\n"
                "x   toggle X11Forwarding\n"
                "e   toggle PermitEmptyPasswords\n"
                "F10 apply   ·   Esc back\n\n"
                "Values flagged in red weaken the server; green ones harden it."
            ),
        )
        self._render()

    def _render(self) -> None:
        s = self._settings
        # Per-directive posture: (value-markup, is_risky).
        root_ok = s.permit_root_login != "yes"
        risks = [not root_ok, s.permit_empty_passwords]
        n = sum(risks)
        summary = (("ok", " ✓ Hardened — no risky directives") if n == 0
                   else ("error", f" ⚠ {n} directive{'s' if n > 1 else ''} weaken this server"))
        self._info.set_text([
            summary, "\n\n",
            ("field", " Port                   : "), f"{s.port}\n",
            ("field", " PermitRootLogin        : "),
            _mark(s.permit_root_login, root_ok, risky=not root_ok), "\n",
            ("field", " PasswordAuthentication : "),
            _mark(_yn(s.password_authentication), not s.password_authentication), "\n",
            ("field", " PubkeyAuthentication   : "),
            _mark(_yn(s.pubkey_authentication), s.pubkey_authentication), "\n",
            ("field", " X11Forwarding          : "),
            _mark(_yn(s.x11_forwarding), not s.x11_forwarding), "\n",
            ("field", " PermitEmptyPasswords   : "),
            _mark(_yn(s.permit_empty_passwords), not s.permit_empty_passwords,
                  risky=s.permit_empty_passwords), "\n",
        ])
        self.app.refresh()

    def handle_key(self, key):
        s = self._settings
        if key == "esc":
            self.app.pop()
            return None
        if key in ("a", "A"):
            self._settings = replace(s, password_authentication=not s.password_authentication)
        elif key in ("k", "K"):
            self._settings = replace(s, pubkey_authentication=not s.pubkey_authentication)
        elif key in ("x", "X"):
            self._settings = replace(s, x11_forwarding=not s.x11_forwarding)
        elif key in ("e", "E"):
            self._settings = replace(s, permit_empty_passwords=not s.permit_empty_passwords)
        elif key in ("r", "R"):
            nxt = ROOT_LOGIN_VALUES[
                (ROOT_LOGIN_VALUES.index(s.permit_root_login) + 1) % len(ROOT_LOGIN_VALUES)]
            self._settings = replace(s, permit_root_login=nxt)
        elif key in ("o", "O"):
            self._edit_port()
            return None
        elif key == "f10":
            self._apply()
            return None
        else:
            return key
        self._render()
        return None

    def _edit_port(self) -> None:
        entry = urwid.Edit("Port: ", str(self._settings.port))

        def save():
            text = entry.edit_text.strip()
            if not text.isdigit() or not valid_port(int(text)):
                self.app.notify("Port must be a number in 1-65535.", error=True)
                return
            self._settings = replace(self._settings, port=int(text))
            self.app.pop()
            self._render()

        modal = Modal(
            self.app, "SSH listen port",
            [urwid.Text(("hint", "The port sshd listens on (default 22).")),
             urwid.Divider(), entry],
            [("Save", save), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 60), height=("relative", 42))

    async def _call(self) -> None:
        settings = self._settings
        backend = SshdBackend()
        try:
            await backend.connect()
            ok, out = await backend.apply_config(settings)
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            with contextlib.suppress(Exception):
                await backend.close()
            return
        with contextlib.suppress(Exception):
            await backend.close()
        self.app.notify(out or ("done" if ok else "failed"), error=not ok)

    def _apply(self) -> None:
        s = self._settings
        warns = []
        if not s.password_authentication and not s.pubkey_authentication:
            warns.append("Both password and pubkey auth are OFF — you could be "
                         "locked out.")
        if s.permit_empty_passwords:
            warns.append("PermitEmptyPasswords is ON — this is unsafe.")

        def go():
            self.app.pop()
            self.app.run_async(self._call())

        body = [urwid.Text(f"Apply the sshd_config changes (port {s.port})?")]
        for w in warns:
            body += [urwid.Divider(), urwid.Text(("error", f" ⚠ {w}"))]
        body += [urwid.Divider(),
                 urwid.Text(("hint", "Validated with sshd -t before it is written."))]
        modal = Modal(self.app, "Apply sshd config", body,
                      [("Apply", go), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 68), height=("relative", 50))
