"""Wi-Fi (wpa_supplicant) in urwid: list, add, remove and scan for networks.

Configured networks are read unprivileged (empty unless GeST runs as root, since
wpa_supplicant.conf is 0600); adding, removing and scanning go through the
polkit-gated WifiBackend, which hashes the passphrase server-side.
"""

from __future__ import annotations

import contextlib

import urwid

from gest.core.wifi import config, reader
from gest.core.wifi.backend_client import WifiBackend
from gest.core.wifi.model import WifiNetwork
from gest.tui.runtime import App, Modal, Screen, boxed


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


class WifiScreen(Screen):
    def __init__(self, app: App) -> None:
        self._networks: list[WifiNetwork] = []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, boxed(self._list, title="Configured networks"),
            title="Wi-Fi (wpa_supplicant)",
            footer_keys=[("a", "Add"), ("s", "Scan"), ("d", "Remove"), ("Esc", "Back")],
        )
        self._load()

    def _load(self) -> None:
        self._networks = reader.configured_networks()
        if self._networks:
            rows = [_row(f"{n.ssid:<32} {'🔒 secured' if n.secured else 'open'}")
                    for n in self._networks]
        else:
            rows = [urwid.Text(" (none configured, or run GeST as root to view)")]
        self._walker[:] = rows
        if self._networks:
            self._walker.set_focus(min(self._walker.focus or 0, len(self._networks) - 1))
        self.app.refresh()

    def _current(self) -> WifiNetwork | None:
        if not self._networks:
            return None
        idx = self._walker.focus
        return self._networks[idx] if idx is not None and 0 <= idx < len(self._networks) else None

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key == "a":
            self._add_form("")
            return None
        if key == "s":
            self.app.run_async(self._scan())
            return None
        if key == "d":
            net = self._current()
            if net is not None:
                self._confirm_remove(net.ssid)
            return None
        return key

    def _add_form(self, ssid_prefill: str) -> None:
        ssid = urwid.Edit("SSID       : ", ssid_prefill)
        passphrase = urwid.Edit("Passphrase : ", mask="*")

        def save():
            s = ssid.edit_text.strip()
            p = passphrase.edit_text
            if not config.valid_ssid(s):
                self.app.notify("Invalid SSID (1-32 characters).", error=True)
                return
            if p and not config.valid_passphrase(p):
                self.app.notify("Passphrase must be 8-63 characters (blank = open).",
                                error=True)
                return
            self.app.pop()
            self.app.run_async(self._call(lambda b: b.add_network(s, p)))

        modal = Modal(
            self.app, "Add Wi-Fi network",
            [urwid.Text(("hint", "Leave the passphrase blank for an open network. "
                                 "It is hashed on the system, never stored in the clear.")),
             urwid.Divider(), ssid, passphrase],
            [("Save", save), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 72), height=("relative", 52))

    def _confirm_remove(self, ssid: str) -> None:
        def go():
            self.app.pop()
            self.app.run_async(self._call(lambda b: b.remove_network(ssid)))

        modal = Modal(
            self.app, "Remove network",
            [urwid.Text(f"Remove the configured network “{ssid}”?")],
            [("Remove", go), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 60), height=("relative", 40))

    async def _call(self, action) -> None:
        backend = WifiBackend()
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
            self._load()

    async def _scan(self) -> None:
        backend = WifiBackend()
        try:
            await backend.connect()
            ok, ssids = await backend.scan()
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            with contextlib.suppress(Exception):
                await backend.close()
            return
        with contextlib.suppress(Exception):
            await backend.close()
        if not ok:
            self.app.notify("No wireless interface, or scan failed.", error=True)
            return
        if not ssids:
            self.app.notify("No networks found.", error=True)
            return
        self.app.push(ScanResultsScreen(self.app, list(ssids), self._add_form))


class ScanResultsScreen(Screen):
    """Nearby SSIDs from a scan; Enter picks one to add."""

    def __init__(self, app: App, ssids: list[str], on_pick) -> None:
        self._ssids = ssids
        self._on_pick = on_pick
        self._walker = urwid.SimpleFocusListWalker([_row(s) for s in ssids])
        super().__init__(
            app, boxed(urwid.ListBox(self._walker), title="Nearby networks"),
            title="Wi-Fi · Scan",
            footer_keys=[("Enter", "Add this network"), ("Esc", "Back")],
        )

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key == "enter" and self._ssids:
            ssid = self._ssids[self._walker.focus]
            self.app.pop()
            self._on_pick(ssid)
            return None
        return key
