"""DNS resolvers (/etc/resolv.conf) and the hosts file (/etc/hosts) in urwid.

Reads are unprivileged; writes go through the polkit-gated NetworkBackend, which
re-validates and writes the whole file atomically.
"""

from __future__ import annotations

import urwid

from gest.core.network import hosts as hosts_core
from gest.core.network import resolv as resolv_core
from gest.core.network.backend_client import NetworkBackend
from gest.core.network.hosts import HostsEntry
from gest.tui.runtime import App, Modal, Screen, boxed


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


async def _apply(app: App, action, *, on_ok=None) -> None:
    backend = NetworkBackend()
    try:
        await backend.connect()
        ok, out = await action(backend)
    except Exception as exc:
        app.notify(str(exc), error=True)
        await backend.close()
        return
    await backend.close()
    app.notify(out or ("done" if ok else "failed"), error=not ok)
    if ok and on_ok is not None:
        on_ok()


class DnsScreen(Screen):
    """Edit the DNS nameservers and search domains in /etc/resolv.conf."""

    def __init__(self, app: App) -> None:
        nameservers, search = resolv_core.current_resolvers()
        self._ns = urwid.Edit("Nameservers (space-separated): ", " ".join(nameservers))
        self._search = urwid.Edit("Search domains (optional)  : ", " ".join(search))
        body = urwid.Filler(
            urwid.Pile([
                urwid.Text(("hint", "One or more DNS server IPs (IPv4 or IPv6).")),
                urwid.Text(("hint", "On a system running dhcpcd/NetworkManager this "
                                    "may be overwritten.")),
                urwid.Divider(),
                self._ns,
                self._search,
                urwid.Divider(),
                urwid.Text("F10 or Enter to apply · Esc to go back."),
            ]),
            valign="top",
        )
        super().__init__(
            app, boxed(body, title="DNS Resolvers"), title="Network · DNS",
            footer_keys=[("Enter", "Apply"), ("Esc", "Back")],
        )

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key in ("enter", "f10"):
            nameservers = self._ns.edit_text.split()
            search = self._search.edit_text.split()
            if not resolv_core.valid_resolv(nameservers, search):
                self.app.notify("Need at least one valid nameserver IP; check domains.",
                                error=True)
                return None
            self.app.run_async(_apply(
                self.app, lambda b: b.set_resolvers(nameservers, search),
                on_ok=self.app.pop))
            return None
        return key


class HostsScreen(Screen):
    """Add/edit/remove /etc/hosts entries; each change rewrites the whole file."""

    def __init__(self, app: App) -> None:
        self._entries: list[HostsEntry] = []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, boxed(self._list, title="/etc/hosts"), title="Network · Hosts",
            footer_keys=[("a", "Add"), ("e", "Edit"), ("d", "Remove"), ("Esc", "Back")],
        )
        self._load()

    def _load(self) -> None:
        self._entries = hosts_core.current_hosts()
        rows = [
            _row(f"{e.address:<39}  {' '.join(e.names)}")
            for e in self._entries
        ] or [urwid.Text(" (no entries)")]
        self._walker[:] = rows
        if self._entries:
            self._walker.set_focus(min(self._walker.focus or 0, len(self._entries) - 1))
        self.app.refresh()

    def _current(self) -> HostsEntry | None:
        if not self._entries:
            return None
        idx = self._walker.focus
        if idx is None or not 0 <= idx < len(self._entries):
            return None
        return self._entries[idx]

    def _persist(self, entries: list[HostsEntry]) -> None:
        if not hosts_core.valid_hosts(entries):
            self.app.notify("Invalid entry (need a valid IP and hostname).", error=True)
            return
        payload = [(e.address, e.names) for e in entries]
        self.app.run_async(_apply(
            self.app, lambda b: b.set_hosts(payload), on_ok=self._load))

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key == "a":
            self._form(None)
            return None
        entry = self._current()
        if key == "e" and entry is not None:
            self._form(entry)
            return None
        if key == "d" and entry is not None:
            self._persist([e for e in self._entries if e is not entry])
            return None
        return key

    def _form(self, entry: HostsEntry | None) -> None:
        editing = entry is not None
        address = urwid.Edit("Address       : ", entry.address if editing else "")
        names = urwid.Edit("Hostnames     : ", " ".join(entry.names) if editing else "")

        def save():
            new = HostsEntry(address.edit_text.strip(), names.edit_text.split())
            if not hosts_core.valid_entry(new):
                self.app.notify("Enter a valid IP and at least one hostname.", error=True)
                return
            if editing:
                updated = [new if e is entry else e for e in self._entries]
            else:
                updated = [*self._entries, new]
            self.app.pop()
            self._persist(updated)

        modal = Modal(
            self.app, "Edit host entry" if editing else "Add host entry",
            [urwid.Text(("hint", "An IP address and one or more space-separated names.")),
             urwid.Divider(), address, names],
            [("Save", save), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 72), height=("relative", 52))
