"""The install wizard's System Role gate (urwid). Headless: construct the screen
over an App and drive keypresses, like the other TUI tests."""

from __future__ import annotations

from gest.core.disk import reader as disk_reader
from gest.tui.runtime import App
from gest.tui.screens.install.role import RoleScreen

_SIZE = (100, 40)


def _render(widget) -> str:
    return "\n".join(row.decode() for row in widget.render(_SIZE, focus=True).text)


def test_role_screen_lists_all_four_roles():
    app = App()
    scr = RoleScreen(app)
    app._stack.append(scr)
    out = _render(scr)
    assert "Desktop (HeDE)" in out
    assert "Server" in out and "Minimal" in out and "Custom" in out
    assert "Recommended" in out                    # desktop is the recommended default


def test_role_screen_focus_starts_on_desktop_and_moves():
    app = App()
    scr = RoleScreen(app)
    app._stack.append(scr)
    assert scr._focused_role() == "desktop"        # first role focused on open
    scr.keypress(_SIZE, "down")
    assert scr._focused_role() == "server"


def test_enter_proposes_and_opens_prefilled_overview(monkeypatch):
    # avoid real lsblk when the overview constructs
    monkeypatch.setattr(disk_reader, "list_block_devices", lambda: [])
    app = App()
    scr = RoleScreen(app)
    app._stack.append(scr)
    scr.keypress(_SIZE, "down")                     # move to Server
    scr.keypress(_SIZE, "enter")                    # choose it
    from gest.tui.screens.installer import InstallOverviewScreen
    top = app._stack[-1]
    assert isinstance(top, InstallOverviewScreen)
    # the overview is pre-filled from assemble.propose("server")
    assert top._sel.role == "server"
    assert top._sel.install_desktop is False
    assert top._sel.admin_model == "traditional"
    assert top._sel.tier2 == {"sshd", "firewall"}


def test_enter_desktop_prefills_rootless(monkeypatch):
    monkeypatch.setattr(disk_reader, "list_block_devices", lambda: [])
    app = App()
    scr = RoleScreen(app)
    app._stack.append(scr)
    scr.keypress(_SIZE, "enter")                    # desktop (first, focused)
    top = app._stack[-1]
    assert top._sel.role == "desktop"
    assert top._sel.admin_model == "rootless" and top._sel.install_desktop is True
