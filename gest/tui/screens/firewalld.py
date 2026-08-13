"""Firewall (firewalld) in urwid: stage service/port allowances, apply as one txn.

Transactional, mirroring the sshd screen: the default zone's *permanent*
services and ports are read as a saved baseline; edits stage against a working
copy shown as "N pending changes" with ● markers for staged adds and a dimmed
"(remove)" for staged removals. F10 opens a diff-review modal and applies the
whole diff through the polkit-gated FirewalldBackend (permanent + reload),
resetting the baseline on success; u discards; Esc prompts when dirty.

Reads are unprivileged; only the apply is privileged.
"""

from __future__ import annotations

import contextlib

import urwid

from gest.core.firewalld import commands, reader
from gest.core.firewalld.backend_client import FirewalldBackend
from gest.core.firewalld.model import ZoneConfig
from gest.tui.runtime import App, Modal, NavPile, Screen, boxed


def _row(markup) -> urwid.Widget:
    """A focusable list row (highlighted blue when focused)."""
    return urwid.AttrMap(urwid.SelectableIcon(markup, 0), None, focus_map="focus")


class FirewalldScreen(Screen):
    def __init__(self, app: App) -> None:
        self._zone = reader.default_zone() or "public"
        self._saved = reader.zone_config(self._zone)   # baseline: permanent config
        self._services: set[str] = set(self._saved.services)  # working copy
        self._ports: set[str] = set(self._saved.ports)
        self._known = reader.known_services()

        self._info = urwid.Text("")
        self._walker = urwid.SimpleFocusListWalker([])
        self._meta: list[tuple[str, str] | None] = []   # per-row (kind, value) or None
        self._list = urwid.ListBox(self._walker)
        self._pile = NavPile([
            ("pack", boxed(self._info, title="firewalld")),
            boxed(self._list, title=f"Zone: {self._zone}  (permanent)"),
        ])
        super().__init__(
            app, self._pile, title="Firewall (firewalld)",
            footer_keys=[
                ("a", "Add service"), ("p", "Add port"), ("d", "Remove"),
                ("F10", "Apply"), ("u", "Discard"), ("Esc", "Back"),
            ],
            help_text=(
                "Manage the default zone's permanent services and ports. Edits are\n"
                "staged as pending changes and applied as one transaction — the\n"
                "backend runs firewall-cmd --permanent for the diff, then --reload.\n\n"
                "a   allow a service (e.g. ssh, http) — name entry\n"
                "p   allow a port (e.g. 22/tcp, 443/tcp, 51820/udp)\n"
                "d/Del  remove the focused item (or un-stage a staged add)\n"
                "F10 review and apply the pending changes\n"
                "u   discard the pending changes\n"
                "Esc back (prompts if changes are pending)\n\n"
                "Staged adds are marked ●; staged removals are dimmed (remove)."
            ),
        )
        self._render()

    # -- staged diff --------------------------------------------------------

    def _diff(self) -> tuple[list[str], list[str], list[str], list[str]]:
        """(add_services, remove_services, add_ports, remove_ports) vs baseline."""
        add_s = sorted(self._services - self._saved.services)
        rem_s = sorted(self._saved.services - self._services)
        add_p = sorted(self._ports - self._saved.ports)
        rem_p = sorted(self._saved.ports - self._ports)
        return add_s, rem_s, add_p, rem_p

    def _pending_count(self) -> int:
        return sum(len(part) for part in self._diff())

    # -- rendering ----------------------------------------------------------

    def _item_markup(self, value: str, *, staged_add: bool, staged_remove: bool):
        if staged_add:
            return [("update", " ● "), ("ok", value)]
        if staged_remove:
            return [("dim", " ○ "), ("dim", f"{value}   (remove)")]
        return ["   ", value]

    def _section(self, title: str, kind: str, saved: frozenset[str],
                 working: set[str]) -> None:
        self._walker.append(urwid.Text(("field", f" {title}")))
        self._meta.append(None)
        names = sorted(saved | working)
        if not names:
            self._walker.append(urwid.Text(("hint", "   (none)")))
            self._meta.append(None)
            return
        for value in names:
            markup = self._item_markup(
                value,
                staged_add=value in working and value not in saved,
                staged_remove=value in saved and value not in working,
            )
            self._walker.append(_row(markup))
            self._meta.append((kind, value))

    def _render(self) -> None:
        pending = self._pending_count()
        n_open = len(self._services) + len(self._ports)
        posture = (("ok", f" ✓ {n_open} allowance{'s' if n_open != 1 else ''} in "
                          f"zone {self._zone}") if n_open
                   else ("hint", f" ○ zone {self._zone} has no service/port allowances"))
        if pending:
            txn = ("update", f" ● {pending} pending change{'s' if pending != 1 else ''} "
                             "— F10 apply · u discard")
        else:
            txn = ("hint", " ○ no pending changes")
        self._info.set_text([posture, "\n", txn])

        focus = self._list.focus_position if self._walker else 0
        self._walker[:] = []
        self._meta = []
        self._section("Services", "service", self._saved.services, self._services)
        self._walker.append(urwid.Divider())
        self._meta.append(None)
        self._section("Ports", "port", self._saved.ports, self._ports)
        if self._walker:
            with contextlib.suppress(IndexError):
                self._list.set_focus(min(focus, len(self._walker) - 1))
        self.app.refresh()

    # -- keys ---------------------------------------------------------------

    def handle_key(self, key):
        if key == "esc":
            if self._pending_count():
                self._confirm_discard_back()
            else:
                self.app.pop()
            return None
        if key in ("a", "A"):
            self._add_service()
            return None
        if key in ("p", "P"):
            self._add_port()
            return None
        if key in ("d", "D", "delete"):
            self._remove_focused()
            return None
        if key in ("u", "U"):
            self._discard()
            return None
        if key == "f10":
            self._apply()
            return None
        return key

    def _remove_focused(self) -> None:
        if not self._walker:
            return
        meta = self._meta[self._list.focus_position]
        if meta is None:
            return
        kind, value = meta
        working = self._services if kind == "service" else self._ports
        # Toggle membership: removes a live/staged allowance (stages a removal or
        # un-stages an add) or re-adds one whose removal was staged.
        if value in working:
            working.discard(value)
        else:
            working.add(value)
        self._render()

    def _discard(self) -> None:
        if not self._pending_count():
            self.app.notify("No pending changes.")
            return
        self._services = set(self._saved.services)
        self._ports = set(self._saved.ports)
        self._render()
        self.app.notify("Pending changes discarded.")

    def _add_service(self) -> None:
        entry = urwid.Edit("Service: ", "")
        sample = ", ".join(sorted(self._known)[:8]) if self._known else "ssh, http, https"

        def save():
            name = entry.edit_text.strip().lower()
            if not commands.valid_service(name):
                self.app.notify("Service names are lowercase letters, digits and dashes.",
                                error=True)
                return
            self._services.add(name)
            self.app.pop()
            self._render()

        modal = Modal(
            self.app, "Allow a service",
            [urwid.Text(("hint", "A firewalld service name (a named port bundle).")),
             urwid.Text(("hint", f"e.g. {sample}")),
             urwid.Divider(), entry],
            [("Add", save), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 66), height=("relative", 48))

    def _add_port(self) -> None:
        entry = urwid.Edit("Port: ", "")

        def save():
            port = entry.edit_text.strip().lower()
            if not commands.valid_port(port):
                self.app.notify("Ports look like 22/tcp or 51820/udp (1-65535).",
                                error=True)
                return
            self._ports.add(port)
            self.app.pop()
            self._render()

        modal = Modal(
            self.app, "Allow a port",
            [urwid.Text(("hint", "A port allowance as N/tcp or N/udp "
                                 "(e.g. 22/tcp, 443/tcp, 51820/udp).")),
             urwid.Divider(), entry],
            [("Add", save), ("Cancel", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 66), height=("relative", 46))

    # -- apply --------------------------------------------------------------

    async def _call(self, add_s, rem_s, add_p, rem_p) -> None:
        backend = FirewalldBackend()
        try:
            await backend.connect()
            ok, out = await backend.apply_changes(
                self._zone, add_s, rem_s, add_p, rem_p)
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            with contextlib.suppress(Exception):
                await backend.close()
            return
        with contextlib.suppress(Exception):
            await backend.close()
        self.app.notify(out or ("done" if ok else "failed"), error=not ok)
        if ok:
            # The transaction committed → the working copy is the new baseline.
            self._saved = ZoneConfig(
                self._zone, frozenset(self._services), frozenset(self._ports))
            self._render()

    def _apply(self) -> None:
        add_s, rem_s, add_p, rem_p = self._diff()
        if not (add_s or rem_s or add_p or rem_p):
            self.app.notify("No pending changes to apply.")
            return

        def go():
            self.app.pop()
            self.app.run_async(self._call(add_s, rem_s, add_p, rem_p))

        body: list = [urwid.Text(("field", f" Pending changes (zone {self._zone}):"))]
        for value in add_s:
            body.append(urwid.Text(["   ", ("field", "service "), ("ok", f"+{value}")]))
        for value in rem_s:
            body.append(urwid.Text(["   ", ("field", "service "), ("error", f"-{value}")]))
        for value in add_p:
            body.append(urwid.Text(["   ", ("field", "port "), ("ok", f"+{value}")]))
        for value in rem_p:
            body.append(urwid.Text(["   ", ("field", "port "), ("error", f"-{value}")]))
        body += [urwid.Divider(),
                 urwid.Text(("hint", "Applied with firewall-cmd --permanent, then "
                                     "--reload to take effect live."))]
        modal = Modal(self.app, "Apply firewall changes", body,
                      [("Apply", go), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 70), height=("relative", 60))

    def _confirm_discard_back(self) -> None:
        n = self._pending_count()

        def go():
            self.app.pop()      # modal
            self.app.pop()      # screen

        modal = Modal(
            self.app, "Discard pending changes?",
            [urwid.Text(f"You have {n} unsaved firewall change{'s' if n != 1 else ''}."),
             urwid.Divider(),
             urwid.Text(("hint", "Going back now discards them (nothing is applied)."))],
            [("Discard & back", go), ("Keep editing", self.app.pop)],
        )
        self.app.push_modal(modal, width=("relative", 62), height=("relative", 44))
