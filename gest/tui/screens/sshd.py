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
        )
        self._render()

    def _render(self) -> None:
        s = self._settings
        def yn(v: bool) -> str:
            return "yes" if v else "no"
        self._info.set_text([
            ("field", " Port                   : "), f"{s.port}\n",
            ("field", " PermitRootLogin        : "), f"{s.permit_root_login}\n",
            ("field", " PasswordAuthentication : "), f"{yn(s.password_authentication)}\n",
            ("field", " PubkeyAuthentication   : "), f"{yn(s.pubkey_authentication)}\n",
            ("field", " X11Forwarding          : "), f"{yn(s.x11_forwarding)}\n",
            ("field", " PermitEmptyPasswords   : "), f"{yn(s.permit_empty_passwords)}\n",
            ("hint", "\n Only these directives are managed; the rest of the file "
                     "is preserved.\n Changes are validated with sshd -t before they "
                     "are applied."),
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
