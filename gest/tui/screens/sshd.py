"""SSH server config in urwid: edit the managed sshd_config directives.

Transactional: edits are staged against a saved baseline, shown as pending
changes, and either applied as one transaction (F10) or discarded (u). Reads are
unprivileged; applying goes through the polkit-gated SshdBackend, which validates
the candidate with `sshd -t` before replacing the live file and reloading the
daemon.
"""

from __future__ import annotations

import contextlib
from dataclasses import replace

import urwid

from gest.core.sshd import reader
from gest.core.sshd.backend_client import SshdBackend
from gest.core.sshd.config import valid_port
from gest.core.sshd.model import ROOT_LOGIN_VALUES, SshdSettings
from gest.tui.runtime import App, Modal, Screen, boxed


def _yn(value: bool) -> str:
    return "yes" if value else "no"


def _fmt(attr: str, value) -> str:
    """Render a directive value for display (bools as yes/no, else str)."""
    return _yn(value) if isinstance(value, bool) else str(value)


# The managed directives, in display order: (label, dataclass field).
_FIELDS: tuple[tuple[str, str], ...] = (
    ("Port", "port"),
    ("PermitRootLogin", "permit_root_login"),
    ("PasswordAuthentication", "password_authentication"),
    ("PubkeyAuthentication", "pubkey_authentication"),
    ("X11Forwarding", "x11_forwarding"),
    ("PermitEmptyPasswords", "permit_empty_passwords"),
)


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
        self._saved = reader.current_settings()      # baseline: what's on disk
        self._settings = self._saved                 # working copy (staged edits)
        self._info = urwid.Text("")
        body = urwid.Filler(boxed(self._info, title="sshd_config"), valign="top")
        super().__init__(
            app, body, title="SSH Server (sshd)",
            footer_keys=[
                ("o", "Port"), ("r", "Root login"), ("a", "Password auth"),
                ("k", "Pubkey auth"), ("x", "X11"), ("e", "Empty pw"),
                ("F10", "Apply"), ("u", "Discard"), ("Esc", "Back"),
            ],
            help_text=(
                "Manage the security-relevant sshd_config directives. Edits are\n"
                "staged as pending changes and applied as one transaction — the\n"
                "candidate is checked with sshd -t before it replaces the file.\n"
                "Every other line in sshd_config is preserved.\n\n"
                "o   set the listen port\n"
                "r   cycle PermitRootLogin (no / prohibit-password /\n"
                "    forced-commands-only / yes)\n"
                "a   toggle PasswordAuthentication\n"
                "k   toggle PubkeyAuthentication\n"
                "x   toggle X11Forwarding\n"
                "e   toggle PermitEmptyPasswords\n"
                "F10 apply the pending changes   ·   u   discard them\n"
                "Esc back (prompts if changes are pending)\n\n"
                "Changed directives are marked ●; values in red weaken the\n"
                "server, green ones harden it."
            ),
        )
        self._render()

    def _pending(self) -> list[tuple[str, str, str]]:
        """Directives that differ from the saved baseline: (label, was, now)."""
        out = []
        for label, attr in _FIELDS:
            was, now = getattr(self._saved, attr), getattr(self._settings, attr)
            if was != now:
                out.append((label, _fmt(attr, was), _fmt(attr, now)))
        return out

    def _value_markup(self, attr: str):
        """Posture-coloured markup for a directive's current (staged) value."""
        s = self._settings
        value = getattr(s, attr)
        if attr == "permit_root_login":
            ok = value != "yes"
            return _mark(value, ok, risky=not ok)
        if attr == "permit_empty_passwords":
            return _mark(_yn(value), not value, risky=value)
        # remaining bools: hardened when the "safe" state holds
        safe = {"password_authentication": not value,
                "pubkey_authentication": value,
                "x11_forwarding": not value}.get(attr)
        if safe is None:                       # Port — neutral
            return str(value)
        return _mark(_yn(value), safe)

    def _render(self) -> None:
        s = self._settings
        pending = self._pending()
        n_risk = sum([s.permit_root_login == "yes", s.permit_empty_passwords])
        posture = (("ok", " ✓ Hardened — no risky directives") if n_risk == 0
                   else ("error", f" ⚠ {n_risk} directive"
                                  f"{'s' if n_risk > 1 else ''} weaken this server"))
        if pending:
            txn = ("update", f" ● {len(pending)} pending change"
                             f"{'s' if len(pending) > 1 else ''} "
                             "— F10 apply · u discard")
        else:
            txn = ("hint", " ○ no pending changes")

        markup: list = [posture, "\n", txn, "\n\n"]
        for label, attr in _FIELDS:
            changed = getattr(self._saved, attr) != getattr(self._settings, attr)
            markup.append(("update", " ● ") if changed else "   ")
            markup.append(("field", f"{label:<22} : "))
            markup.append(self._value_markup(attr))
            if changed:
                markup.append(("dim", f"   (was {_fmt(attr, getattr(self._saved, attr))})"))
            markup.append("\n")
        self._info.set_text(markup)
        self.app.refresh()

    def handle_key(self, key):
        s = self._settings
        if key == "esc":
            if self._pending():
                self._confirm_discard_back()
            else:
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
        elif key in ("u", "U"):
            self._discard()
            return None
        elif key == "f10":
            self._apply()
            return None
        else:
            return key
        self._render()
        return None

    def _discard(self) -> None:
        if not self._pending():
            self.app.notify("No pending changes.")
            return
        self._settings = self._saved
        self._render()
        self.app.notify("Pending changes discarded.")

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

    async def _call(self, settings: SshdSettings) -> None:
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
        if ok:
            self._saved = settings          # the transaction committed → new baseline
            self._render()

    def _apply(self) -> None:
        pending = self._pending()
        if not pending:
            self.app.notify("No pending changes to apply.")
            return
        s = self._settings
        warns = []
        if not s.password_authentication and not s.pubkey_authentication:
            warns.append("Both password and pubkey auth are OFF — you could be "
                         "locked out.")
        if s.permit_empty_passwords:
            warns.append("PermitEmptyPasswords is ON — this is unsafe.")

        def go():
            self.app.pop()
            self.app.run_async(self._call(s))

        body: list = [urwid.Text(("field", " Pending changes:"))]
        for label, was, now in pending:
            body.append(urwid.Text(["   ", ("field", f"{label}: "),
                                    ("dim", was), " → ", ("ok", now)]))
        for w in warns:
            body += [urwid.Divider(), urwid.Text(("error", f" ⚠ {w}"))]
        body += [urwid.Divider(),
                 urwid.Text(("hint", "Validated with sshd -t before it is written."))]
        modal = Modal(self.app, "Apply sshd changes", body,
                      [("Apply", go), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 70), height=("relative", 58))

    def _confirm_discard_back(self) -> None:
        n = len(self._pending())

        def go():
            self.app.pop()      # modal
            self.app.pop()      # screen

        modal = Modal(
            self.app, "Discard pending changes?",
            [urwid.Text(f"You have {n} unsaved sshd change{'s' if n > 1 else ''}."),
             urwid.Divider(),
             urwid.Text(("hint", "Going back now discards them (nothing is written)."))],
            [("Discard & back", go), ("Keep editing", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 62), height=("relative", 44))
