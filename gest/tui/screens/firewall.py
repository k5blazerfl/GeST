"""Firewall (nftables) in urwid: edit a simple stateful policy and apply it.

Reads the current policy from /etc/nftables.nft (unprivileged); rendering the
ruleset and applying it go through the polkit-gated FirewallBackend, which
re-renders server-side. The lower pane previews the exact ruleset that will be
written.
"""

from __future__ import annotations

import contextlib
from dataclasses import replace

import urwid

from gest.core.firewall import nft, reader
from gest.core.firewall.backend_client import FirewallBackend
from gest.core.firewall.model import FirewallPolicy
from gest.tui.runtime import App, Modal, NavPile, Screen, boxed

# When no GeST-managed ruleset exists yet, start from a safe default: drop
# inbound, but keep SSH open so applying can't lock out a remote session.
_DEFAULT = FirewallPolicy(default_input="drop", allow_ping=True, tcp_ports=[22], udp_ports=[])


class FirewallScreen(Screen):
    def __init__(self, app: App) -> None:
        loaded = reader.current_policy()
        self._managed = loaded is not None
        self._policy = loaded or _DEFAULT
        self._info = urwid.Text("")
        self._preview_walker = urwid.SimpleFocusListWalker([urwid.Text(" ")])
        self._preview = urwid.ListBox(self._preview_walker)
        self._pile = NavPile([
            ("pack", boxed(self._info, title="Policy")),
            boxed(self._preview, title="/etc/nftables.nft  (preview)"),
        ])
        super().__init__(
            app, self._pile, title="Firewall (nftables)",
            footer_keys=[
                ("p", "Default policy"), ("i", "Ping"), ("t", "TCP ports"),
                ("u", "UDP ports"), ("F10", "Apply"), ("b", "Enable at boot"),
                ("Esc", "Back"),
            ],
            help_text=(
                "A simple stateful firewall (nftables). Established/related\n"
                "traffic, loopback and IPv6 neighbour discovery are always\n"
                "allowed, so a default-drop policy stays usable.\n\n"
                "p   toggle the default inbound policy\n"
                "    (drop = locked down · accept = permissive)\n"
                "i   allow or block ping (ICMP echo)\n"
                "t   edit the inbound TCP ports to open\n"
                "u   edit the inbound UDP ports to open\n"
                "F10 validate (nft -c) and load the ruleset now\n"
                "b   save the ruleset and enable nftables at boot\n"
                "Esc back\n\n"
                "The lower pane previews the exact /etc/nftables.nft that\n"
                "will be written."
            ),
        )
        self._render()

    def _render(self) -> None:
        p = self._policy
        drop = p.default_input == "drop"
        if not self._managed:
            status = ("hint", " ○ Not applied yet — showing a safe default")
            default_val = ("hint", f"{p.default_input}")
        elif drop:
            status = ("ok", " ● Active — default-drop (locked down)")
            default_val = ("ok", "drop  (deny inbound by default)")
        else:
            status = ("error", " ○ Active — default-accept (permissive)")
            default_val = ("error", "accept  (allow inbound by default)")
        lines = [
            status, "\n\n",
            ("field", " Default inbound : "), default_val, "\n",
            ("field", " Allow ping      : "), f"{'yes' if p.allow_ping else 'no'}\n",
            ("field", " Open TCP ports  : "), f"{_ports(p.tcp_ports)}\n",
            ("field", " Open UDP ports  : "), f"{_ports(p.udp_ports)}",
        ]
        self._info.set_text(lines)
        self._preview_walker[:] = [
            urwid.Text(("dim", line)) for line in nft.render_ruleset(p).splitlines()
        ]
        self.app.refresh()

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
            return None
        if key in ("p", "P"):
            other = "accept" if self._policy.default_input == "drop" else "drop"
            self._policy = replace(self._policy, default_input=other)
            self._render()
            return None
        if key in ("i", "I"):
            self._policy = replace(self._policy, allow_ping=not self._policy.allow_ping)
            self._render()
            return None
        if key in ("t", "T"):
            self._edit_ports("tcp")
            return None
        if key in ("u", "U"):
            self._edit_ports("udp")
            return None
        if key == "f10":
            self._apply()
            return None
        if key in ("b", "B"):
            self._enable_at_boot()
            return None
        return key

    def _edit_ports(self, proto: str) -> None:
        current = self._policy.tcp_ports if proto == "tcp" else self._policy.udp_ports
        entry = urwid.Edit(f"{proto.upper()} ports: ", " ".join(str(p) for p in current))

        def save():
            ports = _parse_ports(entry.edit_text)
            if ports is None:
                self.app.notify("Ports must be numbers in 1-65535.", error=True)
                return
            field = "tcp_ports" if proto == "tcp" else "udp_ports"
            self._policy = replace(self._policy, **{field: ports})
            self.app.pop()
            self._render()

        modal = Modal(
            self.app, f"Open inbound {proto.upper()} ports",
            [urwid.Text(("hint", "Space- or comma-separated port numbers "
                                 "(e.g. 22 80 443). Blank = none.")),
             urwid.Divider(), entry],
            [("Save", save), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 66), height=("relative", 46))

    async def _call(self, action) -> None:
        backend = FirewallBackend()
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
            self._managed = True

    def _apply(self) -> None:
        policy = self._policy

        def go():
            self.app.pop()
            self.app.run_async(self._call(lambda b: b.apply_policy(policy)))

        warn = ("Applying replaces the active firewall ruleset."
                if policy.default_input == "accept"
                else "This drops all inbound traffic except the rules above "
                     "(established, loopback, and the open ports).")
        modal = Modal(
            self.app, "Apply firewall",
            [urwid.Text(("error", f" {warn}")),
             urwid.Divider(),
             urwid.Text("The ruleset is validated (nft -c) before it is loaded.")],
            [("Apply", go), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 66), height=("relative", 48))

    def _enable_at_boot(self) -> None:
        def go():
            self.app.pop()
            self.app.run_async(self._call(lambda b: b.enable_at_boot()))

        modal = Modal(
            self.app, "Enable at boot",
            [urwid.Text("Save the current ruleset and enable the nftables service "
                        "so it is restored on every boot."),
             urwid.Divider(),
             urwid.Text(("hint", "Apply your policy first so the saved ruleset "
                                 "matches it."))],
            [("Enable", go), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 66), height=("relative", 46))


def _ports(ports: list[int]) -> str:
    return " ".join(str(p) for p in ports) if ports else "—"


def _parse_ports(text: str) -> list[int] | None:
    """Parse a space/comma port list into validated ints, or None if any is bad."""
    ports: list[int] = []
    for token in text.replace(",", " ").split():
        if not token.isdigit():
            return None
        port = int(token)
        if not nft.valid_port(port):
            return None
        if port not in ports:
            ports.append(port)
    return ports
