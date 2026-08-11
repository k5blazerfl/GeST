"""Network module in urwid: list interfaces, bring links up/down, edit config.

Reads via `ip -j addr` (unprivileged); link toggles and netifrc config go
through the async NetworkBackend.
"""

from __future__ import annotations

import urwid

from gest.core.network import netifrc, reader
from gest.core.network.backend_client import NetworkBackend
from gest.core.network.model import Interface
from gest.tui.runtime import App, Modal, Screen, boxed


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


class NetworkScreen(Screen):
    def __init__(self, app: App) -> None:
        self._ifaces: dict[str, Interface] = {}
        self._order: list[str] = []
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, boxed(self._list, title="Network interfaces"),
            title="Network",
            footer_keys=[
                ("u", "Up"), ("d", "Down"), ("c", "Configure"),
                ("r", "Refresh"), ("Esc", "Back"),
            ],
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        ifaces = await self.app.run_blocking(reader.list_interfaces)
        self._ifaces = {i.name: i for i in ifaces}
        self._order = [i.name for i in ifaces]
        prev = self._walker.focus if self._walker else 0
        rows = [
            _row(f"{i.name:<16} {('● up' if i.up else i.state.lower()):<10} "
                 f"{i.mac or '—':<18} {' '.join(i.addresses) or '—'}")
            for i in ifaces
        ] or [urwid.Text(" (no interfaces)")]
        self._walker[:] = rows
        if self._order:
            self._walker.set_focus(min(prev or 0, len(self._order) - 1))
        self.app.refresh()

    def _current(self) -> str | None:
        if not self._order:
            return None
        return self._order[self._walker.focus]

    async def _call(self, action, reload: bool = True) -> None:
        backend = NetworkBackend()
        try:
            await backend.connect()
            ok, out = await action(backend)
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        self.app.notify(out or ("done" if ok else "failed"), error=not ok)
        if reload:
            await self._load()

    def handle_key(self, key):
        name = self._current()
        if key == "esc":
            self.app.pop()
            return None
        if key == "r":
            self.app.run_async(self._load())
            return None
        if name is None:
            return key
        if key in ("u", "d"):
            if name == "lo":
                self.app.notify("The loopback interface can't be toggled.", error=True)
            else:
                self.app.run_async(self._call(lambda b: b.set_link(name, key == "u")))
            return None
        if key == "c":
            self._configure(name)
            return None
        return key

    def _configure(self, name: str) -> None:
        if name == "lo":
            self.app.notify("The loopback interface isn't configurable.", error=True)
            return
        cfg = reader.read_interface_config(name)
        dhcp = urwid.CheckBox("Use DHCP (uncheck for static)", state=cfg.method != "static")
        address = urwid.Edit("Static IP (CIDR): ", cfg.address if cfg.method == "static" else "")
        gateway = urwid.Edit("Gateway (optional): ", cfg.gateway if cfg.method == "static" else "")

        def save():
            if dhcp.state:
                self.app.pop()
                self.app.run_async(self._call(
                    lambda b: b.set_interface_config(name, "dhcp"), reload=False))
                return
            addr = address.edit_text.strip()
            gw = gateway.edit_text.strip()
            if not netifrc.valid_address(addr):
                self.app.notify("Enter a valid CIDR address (e.g. 192.168.1.5/24).",
                                error=True)
                return
            if not netifrc.valid_gateway(gw):
                self.app.notify("Invalid gateway address.", error=True)
                return
            self.app.pop()
            self.app.run_async(self._call(
                lambda b: b.set_interface_config(name, "static", addr, gw), reload=False))

        modal = Modal(
            self.app, f"Configure {name}",
            [urwid.Text(f"current: {cfg.method}"), urwid.Divider(), dhcp, address, gateway],
            [("Save", save), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 70), height=("relative", 55))
