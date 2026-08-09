"""Binary package host editor (urwid): list/add/edit/remove binhosts, toggle
the getbinpkg / signature FEATURES, and run getuto to set up trust.

Reading is unprivileged; all changes go through the polkit-gated Portage
backend (WriteConfig / SetupTrust → portage.configure). GeST edits only its own
binrepos.conf/gest.conf; hosts from other fragments are shown read-only.
"""

from __future__ import annotations

import urwid

from gest.core.binhost import reader, writer
from gest.core.binhost.model import GETBINPKG, REQUIRE_SIGNATURE, Binhost, FeaturesState
from gest.core.portage.backend_client import PortageBackend
from gest.tui.runtime import App, Modal, Screen

_HEADER_ROWS = 3  # two FEATURES status lines + a divider precede the host list


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


def _flag(on: bool) -> str:
    return "on " if on else "off"


class BinhostScreen(Screen):
    def __init__(self, app: App) -> None:
        self._hosts: list[Binhost] = []
        self._features = FeaturesState()
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" loading …")])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, urwid.LineBox(self._list, title="Binary package hosts"),
            title="Binhost",
            footer_keys=[
                ("A", "Add"), ("Enter", "Edit"), ("x", "Remove"),
                ("g", "getbinpkg"), ("s", "sig"), ("k", "getuto"), ("Esc", "Back"),
            ],
            help_text=(
                "Binary package hosts let Portage install prebuilt packages "
                "instead of compiling.\n\n"
                "A     add a host to binrepos.conf/gest.conf\n"
                "Enter/e   edit the highlighted (managed) host\n"
                "x     remove the highlighted managed host\n"
                "g     toggle FEATURES=getbinpkg (use binary packages)\n"
                "s     toggle FEATURES=binpkg-request-signature (require signatures)\n"
                "k     run getuto (set up the binary-package trust keyring)\n\n"
                "Hosts from other binrepos.conf fragments are shown read-only."
            ),
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        self._hosts = await self.app.run_blocking(reader.read_all)
        self._features = await self.app.run_blocking(reader.features_state)
        self._render()
        self.app.refresh()

    def _render(self) -> None:
        gbp = _flag(self._features.getbinpkg)
        sig = _flag(self._features.require_signature)
        rows: list[urwid.Widget] = [
            urwid.Text(f"  getbinpkg ....... {gbp}   (g)      "
                       f"binpkg signatures ....... {sig}   (s)"),
            urwid.Text("  k: run getuto (set up binary-package trust)"),
            urwid.Divider("─"),
        ]
        if self._hosts:
            for h in self._hosts:
                tag = " " if h.managed else "·"  # · = external (read-only)
                sig = "✓sig" if h.verify_signature else " nosig"
                prio = f"[{h.priority}]" if h.priority else ""
                rows.append(_row(f"{tag} {h.name:<20} {sig:<6} {prio:<7} {h.sync_uri}"))
        else:
            rows.append(urwid.Text("  (no binhosts configured — press A to add one)"))
        focus = self._walker.focus if self._walker else _HEADER_ROWS
        self._walker[:] = rows
        self._walker.set_focus(min(max(focus, _HEADER_ROWS), len(rows) - 1))

    def _current(self) -> Binhost | None:
        idx = self._walker.focus - _HEADER_ROWS
        if self._hosts and 0 <= idx < len(self._hosts):
            return self._hosts[idx]
        return None

    def handle_key(self, key):
        host = self._current()
        if key == "esc":
            self.app.pop()
        elif key == "A":
            self._edit_modal(None)
        elif key in ("enter", "e") and host is not None:
            if host.managed:
                self._edit_modal(host)
            else:
                self.app.notify("That host is external (read-only here).", error=True)
        elif key == "x" and host is not None:
            if host.managed:
                self._confirm_remove(host.name)
            else:
                self.app.notify("That host is external (read-only here).", error=True)
        elif key == "g":
            self._toggle_feature(GETBINPKG, not self._features.getbinpkg)
        elif key == "s":
            self._toggle_feature(REQUIRE_SIGNATURE, not self._features.require_signature)
        elif key == "k":
            self.app.run_async(self._setup_trust())
        else:
            return key
        return None

    # -- backend plumbing ---------------------------------------------------

    async def _write(self, build) -> None:
        """Build a ConfigWrite off the main loop and apply it, then reload."""
        write = await self.app.run_blocking(build)
        backend = PortageBackend()
        try:
            await backend.connect()
            ok = await backend.write_config([write])
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        if not ok:
            self.app.notify("change was not applied", error=True)
        await self._load()

    def _toggle_feature(self, token: str, enabled: bool) -> None:
        self.app.run_async(self._write(lambda: writer.set_feature(token, enabled)))

    async def _setup_trust(self) -> None:
        backend = PortageBackend()
        try:
            await backend.connect()
            ok, out = await backend.setup_trust()
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        self.app.notify(out.splitlines()[-1] if out else ("getuto done" if ok else "getuto failed"),
                        error=not ok)

    def _apply_host(self, host: Binhost) -> None:
        def build():
            managed = reader.read_managed()
            return writer.write_hosts(writer.upsert_host(managed, host))
        self.app.run_async(self._write(build))

    def _remove(self, name: str) -> None:
        def build():
            managed = reader.read_managed()
            return writer.write_hosts(writer.remove_host(managed, name))
        self.app.run_async(self._write(build))

    # -- modals -------------------------------------------------------------

    def _edit_modal(self, host: Binhost | None) -> None:
        name = urwid.Edit("Name: ", host.name if host else "")
        uri = urwid.Edit("Sync URI: ", host.sync_uri if host else "")
        priority = urwid.Edit("Priority: ", host.priority if host else "")
        verify = urwid.CheckBox("Verify signatures", state=host.verify_signature if host else True)

        def save():
            n = name.edit_text.strip()
            u = uri.edit_text.strip()
            if not n or " " in n:
                self.app.notify("A host name without spaces is required.", error=True)
                return
            if not u:
                self.app.notify("A sync URI is required.", error=True)
                return
            self.app.pop()
            self._apply_host(Binhost(
                name=n, sync_uri=u, priority=priority.edit_text.strip(),
                verify_signature=verify.state, managed=True))

        title = f"Edit binhost “{host.name}”" if host else "Add a binary package host"
        modal = Modal(self.app, title, [name, uri, priority, verify],
                      [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 78), height=("relative", 60))

    def _confirm_remove(self, name: str) -> None:
        def do():
            self.app.pop()
            self._remove(name)

        modal = Modal(self.app, f"Remove binhost “{name}” from gest.conf?", [],
                      [("Remove", do), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 65), height=("relative", 40))
