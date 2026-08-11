"""SSH deploy-key helper (urwid) for private git repositories.

Reached from Software Repositories (key k). Shows root's SSH public key — the
one Portage uses to sync as root — and can generate one if none exists, then
tells the user to paste it into their private overlay's GitHub deploy keys. Only
the public key is shown; the private key stays in /root/.ssh.
"""

from __future__ import annotations

import contextlib

import urwid

from gest.core.repos import sshkey
from gest.core.repos.backend_client import SshBackend
from gest.tui.runtime import App, Screen

_STEPS = (
    "Use this key to sync a private GitHub ebuild overlay over SSH:\n"
    "\n"
    "  1. Copy the public key below (select it in your terminal).\n"
    "  2. On GitHub, open the overlay repo → Settings → Deploy keys →\n"
    "     Add deploy key. Paste it; read-only access is enough.\n"
    "  3. Back here, Add a repository (A) with:\n"
    "        Sync type:  git\n"
    "        Sync URI:   git@github.com:OWNER/REPO.git\n"
    "     then Accept and sync it (Sync Portage Tree).\n"
)


class DeployKeyScreen(Screen):
    def __init__(self, app: App) -> None:
        self._key = urwid.Text(("dim", " Checking for a key …"))
        self._status = urwid.Text("")
        body = urwid.Pile([
            ("pack", urwid.Text(_STEPS)),
            ("pack", urwid.Divider("─")),
            ("pack", urwid.LineBox(self._key, title="root SSH public key")),
            ("pack", self._status),
        ])
        super().__init__(
            app, urwid.Filler(body, valign="top"),
            title="SSH Deploy Key",
            footer_keys=[("g", "Generate"), ("Esc", "Back")],
            help_text=(
                "The root SSH key Portage uses to sync git repositories. For a\n"
                "*private* GitHub overlay, add this public key as a deploy key on\n"
                "the repo (Settings → Deploy keys), then add the repo with sync\n"
                "type git and a git@github.com:owner/repo.git URI.\n\n"
                "g generates a passphraseless ed25519 key at /root/.ssh/id_ed25519\n"
                "if none exists (and seeds github.com into root's known_hosts) —\n"
                "this needs administrator authentication. The private key never\n"
                "leaves /root/.ssh; only the public key is shown. Esc goes back."))
        app.run_async(self._load())

    def _show_key(self, has_key: bool, pub: str) -> None:
        if has_key and pub:
            self._key.set_text(("ok", f" {pub}"))
        else:
            self._key.set_text(
                ("hint", f" No key yet — press g to generate one at "
                         f"{sshkey.KEY_PATH}."))

    def _set_status(self, text: str, attr: str = "field") -> None:
        self._status.set_text((attr, f" {text}"))
        self.app.refresh()

    async def _load(self) -> None:
        backend = SshBackend()
        try:
            await backend.connect()
            has_key, pub, _path = await backend.deploy_key()
        except Exception as exc:
            with contextlib.suppress(Exception):
                await backend.close()
            self._set_status(f"Backend unavailable: {exc}", "error")
            return
        await backend.close()
        self._show_key(has_key, pub)
        self._set_status("Ready." if has_key else
                         "No deploy key yet — press g to generate one.", "dim")
        self.app.refresh()

    async def _generate(self) -> None:
        self._set_status("Generating the deploy key … (authenticate if prompted)")
        backend = SshBackend()
        try:
            await backend.connect()
            ok, pub, _path, message = await backend.ensure_deploy_key()
        except Exception as exc:
            with contextlib.suppress(Exception):
                await backend.close()
            self._set_status(f"Could not create the key: {exc}", "error")
            return
        await backend.close()
        if not ok:
            self._set_status(f"Key generation failed: {message}", "error")
            return
        self._show_key(True, pub)
        self._set_status(f"{message}  Add it as a GitHub deploy key.", "ok")
        self.app.notify("SSH deploy key ready.")

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key in ("g", "G"):
            self.app.run_async(self._generate())
            return None
        return key
