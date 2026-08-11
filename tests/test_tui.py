"""Headless tests for the urwid frontend (drive widgets directly).

These need urwid + a live Portage news source, so they run in the full local
suite rather than the dependency-light CI subset.
"""

import asyncio

import pytest
import urwid

from gest.tui.runtime import App, Screen, ansi_markup, function_bar, strip_ansi
from gest.tui.screens.apply import ApplyScreen
from gest.tui.screens.bootloader import BootloaderScreen
from gest.tui.screens.cleanup import CleanupScreen
from gest.tui.screens.config import KeywordsScreen, UseFlagScreen
from gest.tui.screens.datetime import DateTimeScreen
from gest.tui.screens.disk import DiskScreen
from gest.tui.screens.eselect import EselectScreen
from gest.tui.screens.hardware import HardwareScreen
from gest.tui.screens.logs import LogsScreen
from gest.tui.screens.makeconf import MakeconfScreen
from gest.tui.screens.menu import MenuScreen
from gest.tui.screens.network import NetworkScreen
from gest.tui.screens.news import NewsScreen
from gest.tui.screens.repos import ReposScreen
from gest.tui.screens.services import ServiceDetailScreen, ServicesScreen
from gest.tui.screens.software import SoftwareScreen
from gest.tui.screens.system import HostnameScreen, LocaleScreen, TimezoneScreen
from gest.tui.screens.users import UsersScreen

_SIZE = (100, 30)


def _render(widget) -> str:
    return "\n".join(row.decode() for row in widget.render(_SIZE, focus=True).text)


def test_function_bar_renders_keys():
    canvas = function_bar([("F1", "Help"), ("F9", "Quit")]).render((100,))
    text = "\n".join(row.decode() for row in canvas.text)
    assert "F1" in text and "Help" in text and "F9" in text and "Quit" in text


def test_menu_two_panes_and_category_navigation():
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    out = _render(menu)
    assert "GeST Control Center" in out           # centered title box
    assert "[Help]" in out and "[Quit]" in out and "[Run]" not in out
    assert "Software" in out and "Software Management" in out  # both panes
    menu.keypress(_SIZE, "down")         # move to the System category
    out2 = _render(menu)
    assert "Hostname" in out2 and "Timezone" in out2


def test_quit_is_top_level_only():
    app = App()
    app._unhandled("q")          # a sub-screen's unhandled q must NOT quit
    menu = MenuScreen(app)
    app._stack.append(menu)
    with pytest.raises(urwid.ExitMainLoop):
        menu.keypress(_SIZE, "q")   # but q/Q/F9 quit from the Control Center


def test_f1_opens_help_overlay_with_bespoke_text():
    import urwid
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    menu.keypress(_SIZE, "f1")
    assert isinstance(app._stack[-1], urwid.Overlay)
    assert "Help" in _render(app._stack[-1])


def test_f1_help_synthesized_from_footer_keys():
    import urwid
    app = App()
    scr = HardwareScreen(app)
    app._stack.append(scr)
    scr.keypress(_SIZE, "f1")               # no bespoke help_text -> synthesized
    assert isinstance(app._stack[-1], urwid.Overlay)
    assert "Keys:" in _render(app._stack[-1])


def test_menu_launches_news():
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    menu.keypress(_SIZE, "enter")        # focus the modules pane (Software)
    for _ in range(6):
        menu.keypress(_SIZE, "down")     # to "Portage News"
    menu.keypress(_SIZE, "enter")        # launch
    assert isinstance(app._stack[-1], NewsScreen)


def test_news_loads_items():
    app = App()
    news = NewsScreen(app)
    app._stack.append(news)

    async def _pump():
        for _ in range(100):
            await asyncio.sleep(0.02)
            if news._numbers:
                return

    app.loop.run_until_complete(_pump())
    assert news._numbers  # the live host has Portage news
    assert "[1]" in _render(news)


def test_screen_status_line():
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    app.notify("hello world")
    assert "hello world" in _render(menu)
    assert isinstance(menu, Screen)


def _pump(app, cond, ticks=150):
    async def run():
        for _ in range(ticks):
            await asyncio.sleep(0.02)
            if cond():
                return
    app.loop.run_until_complete(run())


class _FakeSoftwareBackend:
    """A no-op stand-in for the root backend, so TUI tests never touch the real
    system D-Bus service (or run a real emerge sync/update/depclean). Streaming
    ops just report success; refresh-on-open records what it would have synced."""

    synced: list[list[str]] = []
    deselected: list[list[str]] = []

    async def connect(self):
        return self

    async def sync_repos(self, names):
        _FakeSoftwareBackend.synced.append(list(names))
        return (True, "")

    async def deselect(self, atoms):
        _FakeSoftwareBackend.deselected.append(list(atoms))
        return (True, "")

    async def _stream(self, on_progress=None, on_finished=None):
        if on_finished is not None:
            on_finished(0)
        return True

    sync = update_world = _stream

    async def depclean(self, atom="", on_progress=None, on_finished=None):
        return await self._stream(on_progress, on_finished)

    async def depclean_multi(self, atoms, on_progress=None, on_finished=None):
        return await self._stream(on_progress, on_finished)

    async def close(self):
        return None


@pytest.fixture(autouse=True)
def _isolate_software_backend(monkeypatch):
    """The Software modules open a real backend for refresh-on-open and for the
    sync/update/clean-up runs — on a live host that would hit the system D-Bus
    service and run real emerge operations mid test. Swap in a no-op backend for
    every TUI test so nothing touches the real system, regardless of host state."""
    _FakeSoftwareBackend.synced.clear()
    _FakeSoftwareBackend.deselected.clear()
    for mod in ("software", "sync", "update", "cleanup", "accept", "world"):
        monkeypatch.setattr(f"gest.tui.screens.{mod}.SoftwareBackend",
                            _FakeSoftwareBackend, raising=False)


@pytest.fixture(autouse=True)
def _default_accept_manual(monkeypatch):
    """Pin the accept prefs for tests: never read the developer's real prefs, and
    default to manual so review screens don't arm a countdown (or auto-fire mid
    test) unless a test explicitly opts into timer/immediate."""
    monkeypatch.setattr("gest.core.prefs.accept_mode", lambda *a, **k: "manual")
    monkeypatch.setattr("gest.core.prefs.timer_seconds", lambda *a, **k: 5)


def test_menu_launches_services():
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    menu.keypress(_SIZE, "down")   # System
    menu.keypress(_SIZE, "down")   # Hardware
    menu.keypress(_SIZE, "down")   # Storage
    menu.keypress(_SIZE, "down")   # Services
    menu.keypress(_SIZE, "enter")  # focus modules
    menu.keypress(_SIZE, "enter")  # launch Services
    assert isinstance(app._stack[-1], ServicesScreen)


def test_services_list_and_detail():
    app = App()
    scr = ServicesScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._order) > 0)
    assert scr._order  # the live host has OpenRC services
    scr.keypress(_SIZE, "enter")   # open detail for the focused service
    detail = app._stack[-1]
    assert isinstance(detail, ServiceDetailScreen)
    _pump(app, lambda: len(detail._walker) > 1)
    assert "Status:" in _render(detail)
    detail.keypress(_SIZE, "esc")
    assert isinstance(app._stack[-1], ServicesScreen)


def test_services_runlevel_manager_toggles(monkeypatch):
    from gest.core.services.model import Service
    from gest.tui.screens import services as S

    class _FakeServicesBackend:
        calls: list = []

        async def connect(self):
            return self

        async def set_enabled(self, name, enabled, runlevel):
            _FakeServicesBackend.calls.append((name, enabled, runlevel))
            return (True, "")

        async def close(self):
            return None

    fake = [Service(name="sshd", status="started", runlevels=["default"])]
    monkeypatch.setattr(S.reader, "list_services", lambda: fake)
    monkeypatch.setattr(S, "ServicesBackend", _FakeServicesBackend)
    app = App()
    scr = S.ServicesScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: bool(scr._order))
    scr._walker.set_focus(0)
    scr.keypress(_SIZE, "l")                       # open the runlevel manager
    rl = app._stack[-1]
    assert isinstance(rl, S.ServiceRunlevelsScreen)
    out = _render(rl)
    assert "[✓] default" in out and "[ ] boot" in out and "shutdown" in out
    rl._walker.set_focus(1)                        # boot
    rl.keypress(_SIZE, " ")                        # add sshd to boot
    _pump(app, lambda: bool(_FakeServicesBackend.calls))
    assert _FakeServicesBackend.calls == [("sshd", True, "boot")]
    assert "boot" in fake[0].runlevels             # shared Service updated
    assert "[✓] boot" in _render(rl)               # re-rendered with the new mark


def test_hostname_screen_prefills_current():
    app = App()
    scr = HostnameScreen(app)
    app._stack.append(scr)
    assert scr._edit.edit_text  # non-empty current hostname


def test_timezone_screen_loads_and_filters():
    app = App()
    scr = TimezoneScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._all) > 0)
    total = len(scr._all)
    assert total > 100
    scr._filter.set_edit_text("reykjavik")
    assert 0 < len(scr._visible) < total


def test_choice_screen_porous_filter_and_arrow_guard():
    app = App()
    scr = TimezoneScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._all) > 0)
    body = scr._frame.body
    body.focus_position = 1                          # the filter Edit
    scr.keypress(_SIZE, "down")                       # porous: Down leaves into list
    assert body.focus_position == 2
    scr._walker.set_focus(0)
    scr.keypress(_SIZE, "up")                          # up at list top stays put
    assert body.focus_position == 2
    scr.keypress(_SIZE, "tab")                         # Tab returns to the filter
    assert body.focus_position == 1


def test_locale_screen_loads():
    app = App()
    scr = LocaleScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._all) > 0)
    assert scr._all


def test_menu_launches_hostname():
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    menu.keypress(_SIZE, "down")   # System category
    menu.keypress(_SIZE, "enter")  # focus modules (Hostname first)
    menu.keypress(_SIZE, "enter")  # launch Hostname
    assert isinstance(app._stack[-1], HostnameScreen)


def _users_all(app):
    """A UsersScreen forced to the 'all' filter so root is always present
    (the default 'local' filter hides system accounts, and CI may have no
    local login accounts at all)."""
    scr = UsersScreen(app)
    app._stack.append(scr)
    scr._filter = "all"
    app.run_async(scr._load())
    _pump(app, lambda: "root" in scr._order)
    return scr


def test_users_list_and_group_toggle():
    app = App()
    scr = _users_all(app)
    assert scr._order and scr._view == "users"
    assert "root" in _render(scr)
    scr.keypress(_SIZE, "g")
    _pump(app, lambda: scr._view == "groups" and len(scr._order) > 0)
    assert "Groups" in _render(scr)


def test_users_filter_hides_system_accounts():
    app = App()
    scr = UsersScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: scr._loads >= 1)          # default 'local' load done
    assert scr._filter == "local"
    assert "root" not in scr._order              # root is a system account
    n = scr._loads
    scr.keypress(_SIZE, "f")                      # local -> system
    _pump(app, lambda: scr._loads > n)
    assert scr._filter == "system" and "root" in scr._order


def test_users_add_modal_opens_and_cancels():
    app = App()
    scr = _users_all(app)
    scr.keypress(_SIZE, "a")
    assert isinstance(app._stack[-1], urwid.Overlay)
    assert "Add user" in _render(app._stack[-1])
    app._stack[-1].keypress(_SIZE, "esc")
    assert isinstance(app._stack[-1], UsersScreen)


def test_users_edit_modal_prefills():
    app = App()
    scr = _users_all(app)
    scr.keypress(_SIZE, "e")
    assert "Edit user" in _render(app._stack[-1])


def test_users_staged_add_shows_pending_row_and_count():
    from gest.core.users import pending
    app = App()
    scr = _users_all(app)
    assert "No pending changes" in scr._count.text
    scr._pending.stage(pending.add_user_op("newdev", "New Dev", "/bin/bash", "", False))
    scr._after_stage()
    _pump(app, lambda: "newdev" in scr._order)
    idx = scr._order.index("newdev")
    assert scr._walker[idx].base_widget.text.startswith("+")   # staged-add marker
    assert "pending change" in scr._count.text                 # count line updated


def test_users_leaving_edit_surface_prompts_to_save():
    from gest.core.users import pending
    app = App()
    scr = _users_all(app)
    scr._pending.stage(pending.add_user_op("newdev", "New Dev", "/bin/bash", "", False))
    scr._refresh_count()
    scr.keypress(_SIZE, "left")             # users -> auth (leaves editing surface)
    assert isinstance(app._stack[-1], urwid.Overlay)     # save/discard guard modal
    out = _render(app._stack[-1])
    assert "pending change" in out and "Discard" in out and "Keep editing" in out


def test_users_discard_clears_pending():
    from gest.core.users import pending
    app = App()
    scr = _users_all(app)
    scr._pending.stage(pending.add_user_op("newdev", "New Dev", "/bin/bash", "", False))
    scr._refresh_count()
    scr.keypress(_SIZE, "f9")               # Cancel -> discard prompt
    assert isinstance(app._stack[-1], urwid.Overlay)
    app._stack[-1].keypress(_SIZE, "esc")   # keep editing (still staged)
    assert not scr._pending.is_empty


def test_users_defaults_tab_edit_stages_and_shows():
    app = App()
    scr = _users_all(app)
    scr._view = "defaults"
    scr._show_tab()
    _pump(app, lambda: "Defaults for New Users" in _render(scr))
    scr.keypress(_SIZE, "e")                 # open the edit-defaults form
    assert isinstance(app._stack[-1], urwid.Overlay)
    assert "Edit defaults" in _render(app._stack[-1])
    app._stack[-1].keypress(_SIZE, "esc")    # cancel the form
    # stage a defaults change directly and confirm it projects into the tab
    from gest.core.users import pending
    scr._pending.stage(pending.set_defaults_op({"shell": "/bin/zsh"}))
    scr._after_stage()
    _pump(app, lambda: "staged" in _render(scr))
    out = _render(scr)
    assert "/bin/zsh" in out and "staged" in out
    assert "pending change" in scr._count.text


def test_network_list_and_config_modal():
    app = App()
    scr = NetworkScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._order) > 0)
    assert scr._order  # at least loopback
    # focus a non-loopback interface and open the config modal
    for i, name in enumerate(scr._order):
        if name != "lo":
            scr._walker.set_focus(i)
            break
    scr.keypress(_SIZE, "c")
    assert isinstance(app._stack[-1], urwid.Overlay)
    out = _render(app._stack[-1])
    assert "Configure" in out and "Use DHCP" in out
    app._stack[-1].keypress(_SIZE, "esc")
    assert isinstance(app._stack[-1], NetworkScreen)


def _software(app):
    scr = SoftwareScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._cps) > 0, ticks=300)
    return scr


def test_software_two_pane_layout():
    app = App()
    scr = _software(app)
    out = _render(scr)
    assert "Filter" in out and "Packages" in out and "Detail" in out
    assert "Name" in out and "Summary" in out  # pinned column header
    assert "[Cancel]" in out and "[Accept]" in out  # YaST-style action bar


def test_software_refreshes_only_flagged_non_main_repos_on_open(monkeypatch):
    from gest.core.repos.reader import Repo
    from gest.tui.screens import software as sw
    repos = [Repo(name="gentoo", main=True, refresh=True, sync_uri="rsync://x"),
             Repo(name="guru", refresh=True, sync_uri="https://h/guru"),
             Repo(name="off", refresh=False, sync_uri="https://h/off")]
    monkeypatch.setattr(sw.repos_reader, "enabled_repos", lambda: repos)
    app = App()
    _software(app)   # opens the screen (refresh-on-open runs before the load)
    # only the flagged, non-main repo with a sync URI is refreshed
    assert _FakeSoftwareBackend.synced == [["guru"]]


def test_software_loads_marks_and_clears():
    app = App()
    scr = _software(app)
    assert scr._cps  # installed packages
    scr.keypress(_SIZE, "tab")    # sidebar -> table
    assert scr._columns.focus_position == 1
    scr.keypress(_SIZE, " ")      # mark install (installed pkg shows "u")
    assert len(scr._selection) == 1
    assert scr._walker[0].base_widget.text[0] in ("+", "u")
    assert "Accept" in scr._count.text
    scr.keypress(_SIZE, "c")      # clear
    assert scr._selection.is_empty
    assert scr._walker[0].base_widget.text[0] == "i"


def test_software_search_narrows():
    app = App()
    scr = _software(app)
    installed = len(scr._cps)
    scr._columns.focus_position = 0
    scr._sidebar.focus_position = scr._SEARCH_W_IDX
    scr._search.set_edit_text("app-editors/vim")
    scr.keypress(_SIZE, "enter")
    _pump(app, lambda: 0 < len(scr._cps) < installed, ticks=300)
    assert any("vim" in cp for cp in scr._cps)


def test_software_view_switch_to_categories():
    app = App()
    scr = _software(app)
    scr._switch_view("categories")
    _pump(app, lambda: len(scr._categories) > 0, ticks=300)
    assert scr._table_mode == "categories" and scr._categories
    # drill into the first category -> its packages
    scr._columns.focus_position = 1
    scr.keypress(_SIZE, "enter")
    _pump(app, lambda: scr._table_mode == "packages" and scr._drilled is not None, ticks=300)
    assert scr._drilled == scr._categories[0]


def test_software_mode_selector_changes_mode():
    import urwid
    app = App()
    scr = _software(app)
    scr._columns.focus_position = 0
    scr._sidebar.focus_position = scr._MODE_IDX
    scr.keypress(_SIZE, "enter")                  # open the Mode dropdown
    assert isinstance(app._stack[-1], urwid.Overlay)
    drop = app._stack[-1]
    drop.keypress(_SIZE, "down")                  # Contains -> Exact
    drop.keypress(_SIZE, "enter")
    assert scr._mode == "exact"
    assert "Exact" in scr._mode_selector.base_widget.text


def test_software_actions_menu_marks_install():
    import urwid
    app = App()
    scr = _software(app)
    scr.keypress(_SIZE, "tab")                    # focus table
    scr.keypress(_SIZE, "a")                      # open Actions
    assert isinstance(app._stack[-1], urwid.Overlay)
    drop = app._stack[-1]
    drop.keypress(_SIZE, "enter")                 # first item: Install / Update
    assert len(scr._selection) == 1


def test_software_binary_mark_key_and_glyph():
    from gest.core.software import selection as s
    app = App()
    scr = _software(app)
    scr.keypress(_SIZE, "tab")                    # focus table
    scr.keypress(_SIZE, "b")                      # mark install binary-only
    cp = scr._cps[0]
    assert scr._selection.mark_of(cp) == s.BINPKG
    assert scr._walker[0].base_widget.text.startswith("b")   # 'b' glyph
    assert "binary" in scr._count.text


def test_software_binary_menu_opens_binhost():
    from gest.tui.screens.binhost import BinhostScreen
    app = App()
    scr = _software(app)
    # Binary packages menu → sources launches the (now-merged) binhost screen
    scr._on_menu("binary", "binhost")
    assert isinstance(app._stack[-1], BinhostScreen)


def test_software_origin_glyph_source_vs_binary():
    app = App()
    scr = _software(app)
    scr._cps = ["cat/src", "cat/bin"]
    scr._installed = [True, True]
    scr._from_binary = [False, True]
    assert scr._status_for(0, "cat/src") == "i"     # built from source
    assert scr._status_for(1, "cat/bin") == "ⓑ"     # installed from a binary pkg


def test_software_detail_shows_origin():
    from gest.core.software.model import PackageDetail
    app = App()
    scr = _software(app)
    d = PackageDetail(cp="cat/pkg", installed_version="1.0", from_binary=True)
    assert "binary package" in str(scr._render_detail("cat/pkg", d))
    d2 = PackageDetail(cp="cat/pkg", installed_version="1.0", from_binary=False)
    assert "source build" in str(scr._render_detail("cat/pkg", d2))


def test_software_space_cycles_mark_through_binary_and_remove():
    from gest.core.software import selection as s
    app = App()
    scr = _software(app)
    scr.keypress(_SIZE, "tab")                    # focus table
    cp = scr._cps[0]
    scr.keypress(_SIZE, " ")                       # none → install
    assert scr._selection.mark_of(cp) == s.INSTALL
    scr.keypress(_SIZE, " ")                       # install → binary-only
    assert scr._selection.mark_of(cp) == s.BINPKG
    assert scr._walker[0].base_widget.text.startswith("b")
    scr.keypress(_SIZE, " ")                       # binary → remove
    assert scr._selection.mark_of(cp) == s.REMOVE
    assert scr._walker[0].base_widget.text.startswith("-")
    scr.keypress(_SIZE, " ")                       # remove → none
    assert scr._selection.mark_of(cp) is None


def test_software_detail_pane_has_bold_labels():
    app = App()
    scr = _software(app)
    _pump(app, lambda: "Version" in str(scr._detail.get_text()), ticks=300)
    text, attrs = scr._detail.get_text()
    assert "Version:" in text and "Homepage:" in text
    assert "Size:" in text and "Required by:" in text     # phase-A facts
    assert any(attr == "field" for attr, _run in attrs)   # bold field labels
    assert any(attr == "title" for attr, _run in attrs)   # coloured pkg title


def test_software_provides_view_resolves_file_owner():
    app = App()
    scr = _software(app)
    scr._switch_view("provides")
    assert scr._view == "provides" and scr._description_cb is not None
    scr._columns.focus_position = 0
    scr._sidebar.focus_position = scr._SEARCH_W_IDX
    scr._search.set_edit_text("/bin/bash")
    scr.keypress(_SIZE, "enter")
    _pump(app, lambda: any(cp == "app-shells/bash" for cp in scr._cps), ticks=300)
    assert "app-shells/bash" in scr._cps


def test_software_accept_opens_proposal():
    from gest.tui.screens.proposal import ProposalScreen
    app = App()
    scr = _software(app)
    scr.keypress(_SIZE, "tab")    # focus table
    scr.keypress(_SIZE, " ")      # mark one
    scr.keypress(_SIZE, "f10")    # Accept → resolved proposal first
    assert isinstance(app._stack[-1], ProposalScreen)


def test_software_tab_reaches_action_buttons():
    app = App()
    base = urwid.Text("home")
    app._stack.append(base)
    scr = _software(app)
    # start on the columns (sidebar); Tab: sidebar -> table -> actions
    scr._pile.focus_position = 1
    scr._columns.focus_position = 0
    scr.handle_key("tab")                        # sidebar -> table
    scr.handle_key("tab")                        # table -> Cancel
    assert scr._pile.focus_position == 2 and scr._actions.focus is scr._cancel_btn
    scr.handle_key("tab")                        # Cancel -> Accept (Tab within actions)
    assert scr._actions.focus is scr._accept_btn
    scr.handle_key("tab")                        # Accept -> menu
    assert scr._pile.focus_position == 0
    # Enter on the Cancel button pops back
    scr._pile.focus_position = 2
    scr._actions.focus_position = 1               # Cancel
    scr.handle_key("enter")
    assert app._stack[-1] is base


def test_software_shift_tab_backtracks():
    app = App()
    scr = _software(app)
    scr._pile.focus_position = 1
    scr._columns.focus_position = 1               # the table
    scr.keypress(_SIZE, "shift tab")              # table -> sidebar (reverse)
    assert scr._current_pane() == "sidebar"
    scr.keypress(_SIZE, "shift tab")              # sidebar -> menu
    assert scr._current_pane() == "menu"
    scr.keypress(_SIZE, "shift tab")              # menu -> accept (wraps)
    assert scr._current_pane() == "accept"


def test_repos_shift_tab_backtracks():
    app = App()
    scr = ReposScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._repos) > 0, ticks=200)
    body = scr._frame.body
    body.focus_position = 0                        # the repo list
    scr.keypress(_SIZE, "shift tab")               # list -> Accept (reverse wrap)
    assert scr._on_action_row() and scr._actions.focus is scr._actions.buttons[1]


def test_software_accept_button_activates_accept():
    app = App()
    scr = _software(app)
    called = []
    scr._accept = lambda: called.append(1)
    scr._pile.focus_position = 2
    scr._actions.focus_position = 3               # Accept
    scr.handle_key(" ")
    assert called == [1]


def test_software_footer_is_context_sensitive():
    app = App()
    scr = _software(app)

    def bar():
        return scr._footer.contents[1][0].base_widget.text

    # sidebar / search: only search-relevant keys, no package actions
    scr._pile.focus_position = 1
    scr._columns.focus_position = 0
    scr._sidebar.focus_position = scr._SEARCH_W_IDX
    scr._update_footer()
    assert "Search" in bar() and "Mark" not in bar() and "Accept" not in bar()
    # table: the package action keys appear
    scr._columns.focus_position = 1
    scr._update_footer()
    assert "Mark" in bar() and "Accept" in bar()
    # actions: just Activate
    scr._pile.focus_position = 2
    scr._update_footer()
    assert "Activate" in bar() and "Mark" not in bar()


def test_software_arrows_do_not_reach_menu_bar():
    app = App()
    scr = _software(app)
    scr._pile.focus_position = 1
    scr._columns.focus_position = 1               # the package table
    scr._walker.set_focus(0)
    scr.keypress(_SIZE, "up")                      # up at the top of the list
    assert scr._pile.focus_position == 1          # stayed on the columns, not menu
    scr._walker.set_focus(len(scr._cps) - 1)
    scr.keypress(_SIZE, "down")                    # down at the bottom of the list
    assert scr._pile.focus_position == 1          # not the action bar either


def test_proposal_resolves_then_applies(monkeypatch):
    from gest.core.software.preview import PreviewResult
    from gest.tui.screens import proposal as proposal_mod
    from gest.tui.screens.accept import AcceptRunScreen
    from gest.tui.screens.proposal import ProposalScreen
    # canned emerge --pretend output: one new package pulling in one dependency
    monkeypatch.setattr(
        proposal_mod.preview, "preview_install_many",
        lambda atoms, **kw: PreviewResult(" ".join(atoms), 0,
            "[ebuild  N     ] app-editors/vim-9.1  5,000 KiB\n"
            "[ebuild  N     ] dev-libs/libfoo-1.2  1,000 KiB\n"))
    app = App()
    app._stack.append(urwid.Text("software list"))
    scr = ProposalScreen(app, installs=["app-editors/vim"])
    app._stack.append(scr)
    _pump(app, lambda: scr._ready, ticks=200)
    assert scr._ready and scr._n_install == 2      # target + pulled-in dep
    out = _render(scr)
    assert "vim" in out and "libfoo" in out and "Install 2" in out
    scr.keypress(_SIZE, "f10")                      # apply the proposal
    assert isinstance(app._stack[-1], AcceptRunScreen)
    assert not any(isinstance(w, ProposalScreen) for w in app._stack)  # swapped out


def test_proposal_cancel_returns_to_list():
    from gest.tui.screens.proposal import ProposalScreen
    app = App()
    caller = urwid.Text("software list")
    app._stack.append(caller)
    scr = ProposalScreen(app, installs=["app-editors/vim"])
    app._stack.append(scr)
    scr.keypress(_SIZE, "esc")                      # cancel before/after resolving
    assert app._stack[-1] is caller


def _resolved_proposal(monkeypatch, app, mode="timer"):
    """A ProposalScreen (one install) pumped past resolution, in ``mode``."""
    from gest.core.software.preview import PreviewResult
    from gest.tui.screens import proposal as proposal_mod
    from gest.tui.screens.proposal import ProposalScreen
    monkeypatch.setattr("gest.core.prefs.accept_mode", lambda *a, **k: mode)
    monkeypatch.setattr(
        proposal_mod.preview, "preview_install_many",
        lambda atoms, **kw: PreviewResult(" ".join(atoms), 0,
            "[ebuild  N     ] app-editors/vim-9.1  5,000 KiB\n"))
    scr = ProposalScreen(app, installs=["app-editors/vim"])
    app._stack.append(scr)
    _pump(app, lambda: scr._ready, ticks=200)
    return scr


def test_proposal_arms_autoapply_timer(monkeypatch):
    app = App()
    app._stack.append(urwid.Text("software list"))
    scr = _resolved_proposal(monkeypatch, app)
    assert scr._timer_running                       # countdown armed once resolved
    _pump(app, lambda: "applying in" in scr._phase.get_text()[0], ticks=100)
    line = scr._phase.get_text()[0]
    assert "applying in" in line                    # visible countdown
    assert "░" in line or "█" in line               # with a progress bar
    assert ("Enter", "Apply now") in scr._footer_context()


def test_proposal_enter_bypasses_timer_and_applies(monkeypatch):
    from gest.tui.screens.accept import AcceptRunScreen
    from gest.tui.screens.proposal import ProposalScreen
    app = App()
    app._stack.append(urwid.Text("software list"))
    scr = _resolved_proposal(monkeypatch, app)
    scr.keypress(_SIZE, "enter")                    # bypass the countdown, apply now
    assert isinstance(app._stack[-1], AcceptRunScreen)
    assert not any(isinstance(w, ProposalScreen) for w in app._stack)


def test_proposal_esc_stops_timer_then_cancels(monkeypatch):
    app = App()
    caller = urwid.Text("software list")
    app._stack.append(caller)
    scr = _resolved_proposal(monkeypatch, app)
    scr.keypress(_SIZE, "esc")                      # first Esc: stop the countdown
    assert not scr._timer_running
    assert app._stack[-1] is scr                    # stays on the proposal
    assert ("Esc", "Cancel") in scr._footer_context()   # back to manual review
    scr.keypress(_SIZE, "esc")                      # second Esc: cancel back
    assert app._stack[-1] is caller


def test_proposal_countdown_auto_applies(monkeypatch):
    from gest.tui.screens.accept import AcceptRunScreen
    monkeypatch.setattr("gest.core.prefs.timer_seconds", lambda *a, **k: 1)  # fast
    app = App()
    app._stack.append(urwid.Text("software list"))
    _resolved_proposal(monkeypatch, app)
    _pump(app, lambda: isinstance(app._stack[-1], AcceptRunScreen), ticks=300)
    assert isinstance(app._stack[-1], AcceptRunScreen)     # applied on its own


def test_proposal_immediate_mode_applies_without_timer(monkeypatch):
    from gest.tui.screens.accept import AcceptRunScreen
    app = App()
    app._stack.append(urwid.Text("software list"))
    _resolved_proposal(monkeypatch, app, mode="immediate")
    assert isinstance(app._stack[-1], AcceptRunScreen)     # applied at once


def _cleanup_with_orphans(monkeypatch, app, mode="timer"):
    """A CleanupScreen scanned to one orphan in ``mode``; ``_clean`` is spied.

    Returns ``(screen, cleaned)`` where ``cleaned`` records _clean() calls, so a
    test can assert the run was launched without actually starting emerge."""
    from gest.core.software import cleanup as core_cleanup
    from gest.core.software.cleanup import CleanupPlan, Orphan
    from gest.tui.screens.cleanup import CleanupScreen
    plan = CleanupPlan(
        orphans=[Orphan(cp="games-board/freecell", version="1.0", size=1024)],
        counts={"installed": 1}, ok=True)
    monkeypatch.setattr(core_cleanup, "plan_cleanup", lambda **kw: plan)
    monkeypatch.setattr("gest.core.prefs.accept_mode", lambda *a, **k: mode)
    cleaned: list = []
    monkeypatch.setattr(CleanupScreen, "_clean", lambda self: cleaned.append(True))
    scr = CleanupScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: scr._armed, ticks=300)
    return scr, cleaned


def test_cleanup_arms_timer_and_enter_cleans(monkeypatch):
    app = App()
    app._stack.append(urwid.Text("menu"))
    scr, cleaned = _cleanup_with_orphans(monkeypatch, app, mode="timer")
    assert scr._timer_running                       # countdown armed after scan
    assert ("Enter", "Clean up now") in scr._footer_context()
    scr.keypress(_SIZE, "enter")                    # bypass → clean now
    assert cleaned == [True] and not scr._timer_running


def test_cleanup_esc_stops_timer_without_leaving(monkeypatch):
    app = App()
    caller = urwid.Text("menu")
    app._stack.append(caller)
    scr, cleaned = _cleanup_with_orphans(monkeypatch, app, mode="timer")
    scr.keypress(_SIZE, "esc")                      # first Esc: stop the countdown
    assert not scr._timer_running and cleaned == []
    assert app._stack[-1] is scr                    # stays on Clean Up
    scr.keypress(_SIZE, "esc")                      # second Esc: back to menu
    assert app._stack[-1] is caller


def test_cleanup_immediate_mode_cleans_at_once(monkeypatch):
    app = App()
    app._stack.append(urwid.Text("menu"))
    scr, cleaned = _cleanup_with_orphans(monkeypatch, app, mode="immediate")
    assert cleaned == [True]                         # cleaned without a countdown
    assert not scr._timer_running


def test_preferences_screen_selects_and_saves(monkeypatch):
    from gest.core import prefs
    from gest.tui.screens.preferences import PreferencesScreen
    store = {"v": prefs.MANUAL}
    monkeypatch.setattr("gest.core.prefs.accept_mode", lambda *a, **k: store["v"])
    monkeypatch.setattr("gest.core.prefs.set_accept_mode",
                        lambda mode, *a, **k: store.__setitem__("v", mode))
    app = App()
    scr = PreferencesScreen(app)
    app._stack.append(scr)
    out = _render(scr)
    assert all(s in out for s in
               ("Click to accept", "Countdown timer", "As soon as ready"))
    assert "(•) Click to accept" in out             # current = manual
    scr._walker.set_focus(1)                        # Countdown timer
    scr.keypress(_SIZE, "enter")                    # select it (saves)
    assert store["v"] == prefs.TIMER
    assert "(•) Countdown timer" in _render(scr)


def test_preferences_screen_adjusts_timer_length(monkeypatch):
    from gest.core import prefs
    from gest.tui.screens.preferences import PreferencesScreen
    store = {"mode": prefs.TIMER, "secs": 5}
    monkeypatch.setattr("gest.core.prefs.accept_mode", lambda *a, **k: store["mode"])
    monkeypatch.setattr("gest.core.prefs.timer_seconds", lambda *a, **k: store["secs"])
    monkeypatch.setattr("gest.core.prefs.set_timer_seconds",
                        lambda s, *a, **k: store.__setitem__("secs", s))
    app = App()
    scr = PreferencesScreen(app)
    app._stack.append(scr)
    scr._walker.set_focus(len(scr._items) - 1)      # the Timer length row
    assert ("←/→", "Adjust") in scr._footer_context()
    assert "5 seconds" in _render(scr)
    scr.keypress(_SIZE, "right")                    # 5 -> 6
    scr.keypress(_SIZE, "right")                    # 6 -> 7
    assert store["secs"] == 7 and "7 seconds" in _render(scr)
    scr.keypress(_SIZE, "left")                     # 7 -> 6
    assert store["secs"] == 6



def test_apply_progress_parses_emerge_markers():
    from gest.core.software.preview import PreviewResult
    from gest.tui.screens.apply import Plan
    app = App()
    # A stub plan keeps the preview fast (no real emerge --pretend) so the
    # screen's _preview coroutine completes and is properly awaited.
    stub = Plan("Install", lambda: PreviewResult("x", 0, "Total: 5 packages"),
                lambda b, p, f: True)
    scr = ApplyScreen(app, [stub], verb="Accept")
    _pump(app, lambda: scr._ready, ticks=50)
    scr._plan_label = "Install"
    scr._update_progress(">>> Emerging (2 of 5) app-editors/vim-9.1::gentoo")
    assert scr._bar.done == 5 and scr._bar.current == 1   # emerging 2 → 1 complete
    assert "2 of 5" in scr._phase.text and "vim" in scr._phase.text
    scr._update_progress(">>> Installing (2 of 5) app-editors/vim-9.1::gentoo")
    assert scr._bar.current == 2                          # installing 2 → 2 complete
    scr._update_progress(">>> Emerging binary (3 of 5) sys-apps/foo-1.0::gentoo")
    assert scr._bar.current == 2 and "3 of 5" in scr._phase.text
    scr._update_progress("Calculating dependencies... done!")   # non-marker ignored
    assert scr._bar.current == 2


def test_apply_completion_modal_success_and_failure():
    import urwid

    from gest.core.software.preview import PreviewResult
    from gest.tui.screens.apply import Plan
    app = App()
    stub = Plan("Install", lambda: PreviewResult("x", 0, "Total: 1 package"),
                lambda b, p, f: True)
    scr = ApplyScreen(app, [stub], verb="Accept")
    app._stack.append(scr)
    _pump(app, lambda: scr._ready, ticks=50)
    # success prompt appears, names the outcome, and 'View log' (esc) returns
    scr._finish("Completed", True, "all good")
    assert isinstance(app._stack[-1], urwid.Overlay)
    out = _render(app._stack[-1])
    assert "Completed" in out and "all good" in out
    app._stack[-1].keypress(_SIZE, "esc")               # View log
    assert isinstance(app._stack[-1], ApplyScreen)
    # failure prompt likewise
    scr._finish("Failed", False, "emerge exited 1")
    assert "Failed" in _render(app._stack[-1])


def test_apply_log_is_bounded_and_spills_to_file():
    """A failing build streams a huge log; the on-screen scrollback must stay
    bounded (memory/redraw safety) while the full log lands on disk."""
    import os

    from gest.core.software.preview import PreviewResult
    from gest.tui.screens.apply import _MAX_LOG_LINES, Plan
    app = App()
    stub = Plan("Install", lambda: PreviewResult("x", 0, "Total: 1 package"),
                lambda b, p, f: True)
    scr = ApplyScreen(app, [stub], verb="Accept")
    _pump(app, lambda: scr._ready, ticks=50)

    total = _MAX_LOG_LINES * 3
    for i in range(total):
        scr._append([f"build line {i}"])

    # Scrollback is capped, and it kept the *tail* (the error end of a failure).
    assert len(scr._walker) <= _MAX_LOG_LINES
    assert f"build line {total - 1}" in scr._walker[-1].text
    # The complete log spilled to disk — nothing lost for debugging.
    scr._close_log()
    with open(scr._logpath) as fh:
        contents = fh.read()
    assert "build line 0" in contents and f"build line {total - 1}" in contents
    assert contents.count("\n") >= total
    os.unlink(scr._logpath)


def test_apply_refresh_is_coalesced():
    """Streaming N lines must not trigger N full redraws; a burst collapses to
    a single scheduled draw."""
    from gest.core.software.preview import PreviewResult
    from gest.tui.screens.apply import Plan
    app = App()
    stub = Plan("Install", lambda: PreviewResult("x", 0, "Total: 1 package"),
                lambda b, p, f: True)
    scr = ApplyScreen(app, [stub], verb="Accept")
    _pump(app, lambda: scr._ready, ticks=50)

    calls = {"n": 0}
    app.refresh = lambda: calls.__setitem__("n", calls["n"] + 1)
    for i in range(500):
        scr._append([f"line {i}"])          # a burst within one loop tick
    assert scr._refresh_pending             # one draw scheduled, not 500
    scr._flush_refresh()
    assert calls["n"] == 1
    scr._close_log()
    import os
    os.unlink(scr._logpath)


def _sync_apply_screen(app):
    from gest.core.software.preview import PreviewResult
    from gest.tui.screens.apply import Plan
    stub = Plan("Sync", lambda: PreviewResult("x", 0, "sync"), lambda b, p, f: True)
    scr = ApplyScreen(app, [stub], verb="Sync")
    _pump(app, lambda: scr._ready, ticks=50)
    return scr


def test_apply_captures_per_repo_sync_results():
    """The real `emerge --sync` summary lines are parsed into per-repo codes."""
    app = App()
    scr = _sync_apply_screen(app)
    for line in [
        "Action: sync for repo: gentoo, returned code = 0",
        ">>> Syncing repository 'zGentoo' ...",   # noise, ignored
        "Action: sync for repo: zGentoo, returned code = 1",
        "Action: sync for repo: amphitheater, returned code = 0",
    ]:
        scr._note_sync_result(line)
    assert scr._sync_results == {"gentoo": 0, "zGentoo": 1, "amphitheater": 0}


def test_apply_sync_outcome_partial_is_not_flat_failure():
    """A mix of ok/failed repos → 'Partially synced', naming the culprit — not a
    flat 'Failed'. This is the reported symptom: a working sync read as failed."""
    app = App()
    scr = _sync_apply_screen(app)

    # No sync lines seen → generic wording (returns None, caller uses old path).
    assert scr._sync_outcome(0) is None

    # All succeeded → Completed, listing repos.
    scr._sync_results = {"gentoo": 0, "amphitheater": 0}
    title, ok, msg = scr._sync_outcome(0)
    assert title == "Completed" and ok is True and "gentoo" in msg

    # One overlay failed while the tree synced → partial, not failure.
    scr._sync_results = {"gentoo": 0, "zGentoo": 1}
    title, ok, msg = scr._sync_outcome(1)
    assert title == "Partially synced" and ok is False
    assert "✓ gentoo" in msg and "✗ zGentoo (code 1)" in msg

    # Everything failed → genuine failure.
    scr._sync_results = {"gentoo": 1, "zGentoo": 1}
    title, ok, msg = scr._sync_outcome(1)
    assert title == "Failed" and ok is False


def test_menu_launches_software():
    from gest.tui.screens.software import SoftwareLoadingScreen
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    menu.keypress(_SIZE, "enter")  # Software category -> modules (Software Mgmt first)
    menu.keypress(_SIZE, "enter")  # launch
    # the fullscreen loading screen opens first, then hands off to SoftwareScreen
    assert isinstance(app._stack[-1], SoftwareLoadingScreen)
    _pump(app, lambda: isinstance(app._stack[-1], SoftwareScreen), ticks=400)
    assert isinstance(app._stack[-1], SoftwareScreen)


def test_software_loading_screen_shows_steps_and_hands_off():
    from gest.tui.screens.software import SoftwareLoadingScreen
    app = App()
    scr = SoftwareLoadingScreen(app)
    app._stack.append(scr)
    out = _render(scr)
    assert "Starting Package Management" in out
    assert "########" in out                      # the ASCII GeST logo
    assert "Refresh repositories" in out and "Load installed packages" in out
    _pump(app, lambda: isinstance(app._stack[-1], SoftwareScreen), ticks=400)
    handed = app._stack[-1]
    assert isinstance(handed, SoftwareScreen) and handed._cps  # loaded + handed over


def test_useflag_editor_loads_and_cycles():
    app = App()
    scr = UseFlagScreen(app, "app-editors/vim")
    app._stack.append(scr)
    _pump(app, lambda: len(scr._flags) > 0, ticks=300)
    assert scr._flags
    first = scr._flags[0]
    before = scr._states[first]
    scr.keypress(_SIZE, " ")
    assert scr._states[first] != before  # tri-state cycle


def test_keywords_editor_cycles():
    app = App()
    scr = KeywordsScreen(app, "app-editors/vim")
    app._stack.append(scr)
    before = scr._kw
    scr.keypress(_SIZE, " ")   # focus is on the keyword row
    assert scr._kw != before


def test_software_u_opens_use_editor():
    app = App()
    scr = _software(app)
    scr.keypress(_SIZE, "tab")   # focus table
    scr.keypress(_SIZE, "u")
    assert isinstance(app._stack[-1], UseFlagScreen)


def test_eselect_footer_and_tab_track_the_focused_column():
    app = App()
    scr = EselectScreen(app)
    app._stack.append(scr)
    scr._columns.focus_position = 0
    scr._refresh_footer()
    assert any(lbl == "Targets" for _k, lbl in scr._footer_context())
    scr.keypress(_SIZE, "tab")                    # Tab mirrors → : Modules -> Targets
    assert scr._columns.focus_position == 1
    assert any(lbl == "Modules" for _k, lbl in scr._footer_context())


def test_users_footer_changes_per_tab():
    app = App()
    scr = _users_all(app)
    scr._do_switch("users")
    assert any(k == "f" for k, _lbl in scr._footer_context())   # filter on users
    scr._do_switch("auth")                        # read-only tab
    ctx = scr._footer_context()
    assert not any(k in ("a", "e", "d") for k, _lbl in ctx)     # no edit keys
    # a focused action button shows the activate key set
    body = scr._frame.body
    body.focus_position = scr._cycle_action_pos
    assert any(lbl == "Activate" for _k, lbl in scr._footer_context())


def test_eselect_lists_modules_and_targets():
    app = App()
    scr = EselectScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._modules) > 0, ticks=300)
    assert scr._modules  # eselect modules on the host
    # move to the kernel module and check its targets load
    for i, m in enumerate(scr._modules):
        if m.name == "kernel":
            scr._mod_walker.set_focus(i)
            break
    _pump(app, lambda: scr._current_module == "kernel" and len(scr._targets) > 0, ticks=300)
    assert any(t.current for t in scr._targets)


def test_menu_launches_eselect():
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    menu.keypress(_SIZE, "down")   # System category
    menu.keypress(_SIZE, "enter")  # focus modules
    for _ in range(3):
        menu.keypress(_SIZE, "down")  # hostname/timezone/locale -> eselect (4th)
    menu.keypress(_SIZE, "enter")
    assert isinstance(app._stack[-1], EselectScreen)


def test_hardware_lists_sections_and_details():
    app = App()
    scr = HardwareScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._sections) > 0, ticks=300)
    assert any(s.key == "cpu" for s in scr._sections)  # every host has a CPU
    out = _render(scr)
    assert "Hardware" in out and "CPU" in out
    # focusing the CPU section fills the detail pane with its lines
    for i, s in enumerate(scr._sections):
        if s.key == "cpu":
            scr._cat_walker.set_focus(i)
            break
    assert scr._detail_walker  # details populated


def test_menu_launches_hardware():
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    menu.keypress(_SIZE, "down")   # System
    menu.keypress(_SIZE, "down")   # Hardware
    menu.keypress(_SIZE, "enter")  # focus modules
    menu.keypress(_SIZE, "enter")  # launch the single module
    assert isinstance(app._stack[-1], HardwareScreen)


def test_disk_lists_devices_and_fstab():
    app = App()
    scr = DiskScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._entries) > 0, ticks=300)
    assert scr._entries  # the host has fstab entries
    out = _render(scr)
    assert "Block Devices" in out and "/etc/fstab" in out


def test_disk_tab_switches_panes_and_arrows_stay():
    app = App()
    scr = DiskScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._entries) > 0, ticks=300)
    pile = scr._frame.body
    pile.focus_position = 1                            # the fstab list
    scr._fstab_walker.set_focus(0)
    scr.keypress(_SIZE, "up")                           # must not jump to devices
    assert pile.focus_position == 1
    scr.keypress(_SIZE, "tab")                          # Tab switches panes
    assert pile.focus_position == 0
    assert any(lbl in ("fstab",) for _k, lbl in scr._footer_context())
    # the root filesystem is present and flagged protected
    assert any(e.mountpoint == "/" and e.protected for e in scr._entries)


def test_menu_launches_disk():
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    menu.keypress(_SIZE, "down")   # System
    menu.keypress(_SIZE, "down")   # Hardware
    menu.keypress(_SIZE, "down")   # Storage
    menu.keypress(_SIZE, "enter")  # focus modules
    menu.keypress(_SIZE, "enter")  # launch Disks & Mounts
    assert isinstance(app._stack[-1], DiskScreen)


def test_logs_lists_sources_and_view():
    app = App()
    scr = LogsScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._sources) > 0, ticks=300)
    assert scr._sources                        # at least the dmesg source
    out = _render(scr)
    assert "Logs" in out and "View" in out


def test_menu_launches_logs():
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    for _ in range(7):             # -> Miscellaneous (8th category)
        menu.keypress(_SIZE, "down")
    menu.keypress(_SIZE, "enter")  # focus modules
    menu.keypress(_SIZE, "enter")  # launch System Logs
    assert isinstance(app._stack[-1], LogsScreen)


def test_datetime_loads_clock_info():
    app = App()
    scr = DateTimeScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: scr._info is not None, ticks=300)
    out = _render(scr)
    assert "Local time" in out and "Timezone" in out and "NTP sync" in out


def test_menu_launches_datetime():
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    menu.keypress(_SIZE, "down")   # System category
    menu.keypress(_SIZE, "enter")  # focus modules
    for _ in range(6):             # -> datetime (7th System module)
        menu.keypress(_SIZE, "down")
    menu.keypress(_SIZE, "enter")
    assert isinstance(app._stack[-1], DateTimeScreen)


def test_bootloader_shows_info():
    app = App()
    scr = BootloaderScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: "Running kernel" in scr._info.text, ticks=200)
    assert "Running kernel" in scr._info.text
    assert "Bootloader" in scr._info.text


def test_menu_launches_bootloader():
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    menu.keypress(_SIZE, "down")   # System category
    menu.keypress(_SIZE, "enter")  # focus modules
    for _ in range(4):
        menu.keypress(_SIZE, "down")  # hostname/timezone/locale/eselect -> bootloader (5th)
    menu.keypress(_SIZE, "enter")
    assert isinstance(app._stack[-1], BootloaderScreen)


def test_strip_ansi_removes_colour_codes():
    assert strip_ansi("\x1b[32m*\x1b[0m done") == "* done"
    assert strip_ansi("\x1b[1;31mERROR\x1b[0m") == "ERROR"
    assert strip_ansi("plain text") == "plain text"
    assert strip_ansi("\x1b]0;title\x07after") == "after"  # OSC title


def test_ansi_markup_parses_colours():
    assert ansi_markup("\x1b[32m*\x1b[0m done") == [("ansi32", "*"), " done"]
    assert ansi_markup("\x1b[1;31mERROR\x1b[0m") == [("ansib31", "ERROR")]
    assert ansi_markup("\x1b[92mOK\x1b[0m") == [("ansib32", "OK")]  # bright -> bold
    assert ansi_markup("plain") == "plain"                            # no colour -> str
    assert ansi_markup("\x1b]0;t\x07\x1b[33m>>>\x1b[0m go") == [("ansi33", ">>>"), " go"]


def test_makeconf_lists_and_opens_edit():
    import urwid
    app = App()
    scr = MakeconfScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._vars) > 0, ticks=200)
    assert scr._vars  # this host has a make.conf
    scr.keypress(_SIZE, "enter")
    assert isinstance(app._stack[-1], urwid.Overlay)   # edit modal
    app._stack[-1].keypress(_SIZE, "esc")
    assert isinstance(app._stack[-1], MakeconfScreen)


def test_menu_launches_makeconf():
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    menu.keypress(_SIZE, "down")   # System category
    menu.keypress(_SIZE, "enter")  # focus modules
    for _ in range(5):
        menu.keypress(_SIZE, "down")  # -> makeconf (6th System module)
    menu.keypress(_SIZE, "enter")
    assert isinstance(app._stack[-1], MakeconfScreen)


def test_software_menu_bar_opens_and_selects():
    import urwid

    from gest.tui.screens.news import NewsScreen
    app = App()
    scr = _software(app)
    # focus the menu bar, open Extras, pick "Portage news"
    scr._pile.focus_position = 0
    assert scr._pile.focus_position == 0
    for _ in range(4):
        # View -> Configuration -> Binary packages -> Dependencies -> Extras
        scr.keypress(_SIZE, "right")
    scr.keypress(_SIZE, "enter")                  # open Extras dropdown
    assert isinstance(app._stack[-1], urwid.Overlay)
    drop = app._stack[-1]
    drop.keypress(_SIZE, "down")
    drop.keypress(_SIZE, "down")                  # -> Portage news
    drop.keypress(_SIZE, "enter")
    assert isinstance(app._stack[-1], NewsScreen)


def test_repos_lists_enabled_and_marks_main():
    app = App()
    scr = ReposScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._repos) > 0, ticks=200)
    assert scr._repos                      # this host has repos.conf
    assert any(r.main for r in scr._repos)  # the main repo is flagged
    body = _render(scr)
    assert "\u2605" in body                 # ★ marker on the main repo


def test_repos_add_modal_opens_and_cancels():
    app = App()
    scr = ReposScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._repos) > 0, ticks=200)
    scr.keypress(_SIZE, "A")
    assert isinstance(app._stack[-1], urwid.Overlay)   # add modal
    app._stack[-1].keypress(_SIZE, "esc")
    assert isinstance(app._stack[-1], ReposScreen)


def test_repos_protects_main_repo():
    app = App()
    scr = ReposScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._repos) > 0, ticks=200)
    for i, r in enumerate(scr._repos):
        if r.main:
            scr._walker.set_focus(i)
            break
    scr.keypress(_SIZE, "x")                # remove main -> blocked, no confirm modal
    assert isinstance(app._stack[-1], ReposScreen)


def _focus_main(scr):
    for i, r in enumerate(scr._repos):
        if r.main:
            scr._walker.set_focus(i)
            return r
    return None


def test_repos_mirror_opens_only_for_main_repo():
    from gest.tui.screens.mirrors import MirrorScreen
    app = App()
    scr = ReposScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._repos) > 0, ticks=200)
    # a non-main repo: m is rejected
    non_main = next((i for i, r in enumerate(scr._repos) if not r.main), None)
    if non_main is not None:
        scr._walker.set_focus(non_main)
        scr.keypress(_SIZE, "m")
        assert isinstance(app._stack[-1], ReposScreen)
    # the ★ main repo: m opens the mirror picker
    _focus_main(scr)
    scr.keypress(_SIZE, "m")
    assert isinstance(app._stack[-1], MirrorScreen)
    out = _render(app._stack[-1])
    assert "rsync mirrors" in out and "Germany" in out


def test_mirror_screen_applies_selection(monkeypatch):
    from gest.tui.screens import mirrors as mirror_screen
    from gest.tui.screens.mirrors import MirrorScreen
    captured = {}

    class _FakePortageBackend:
        async def connect(self):
            return self

        async def write_config(self, writes):
            captured["writes"] = list(writes)
            return True

        async def close(self):
            return None

    monkeypatch.setattr(mirror_screen, "PortageBackend", _FakePortageBackend)
    monkeypatch.setattr(mirror_screen, "_read_text",
                        lambda _p: "[gentoo]\nsync-uri = rsync://old/gentoo-portage\n")
    app = App()
    caller = urwid.Text("repos")
    app._stack.append(caller)
    scr = MirrorScreen(app, repo="gentoo", current="rsync://old/gentoo-portage")
    app._stack.append(scr)
    scr._choose("rsync://rsync.de.gentoo.org/gentoo-portage")
    _pump(app, lambda: "writes" in captured, ticks=100)
    cw = captured["writes"][0]
    assert cw.path.endswith("repos.conf/gentoo.conf")
    assert "sync-uri = rsync://rsync.de.gentoo.org/gentoo-portage" in cw.text
    assert "rsync://old" not in cw.text
    assert app._stack[-1] is caller          # returned to the caller after applying


def test_repos_edit_opens_form_for_enabled_repo():
    app = App()
    scr = ReposScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._repos) > 0, ticks=200)
    idx = next((i for i, r in enumerate(scr._repos) if r.enabled), None)
    if idx is None:
        pytest.skip("no enabled repository configured on this host")
    scr._walker.set_focus(idx)
    scr.keypress(_SIZE, "e")
    assert isinstance(app._stack[-1], urwid.Overlay)   # the edit form modal
    out = _render(app._stack[-1])
    assert "Edit repository" in out and "Sync URI" in out and "Priority" in out


def test_repos_edit_applies_config_write(monkeypatch):
    from gest.core.repos.reader import Repo
    from gest.tui.screens import repos as repos_mod
    captured = {}

    class _FakePortageBackend:
        async def connect(self):
            return self

        async def write_config(self, writes):
            captured["writes"] = list(writes)
            return True

        async def close(self):
            return None

    monkeypatch.setattr(repos_mod, "PortageBackend", _FakePortageBackend)
    monkeypatch.setattr(
        repos_mod.edit, "locate",
        lambda _conf, name: (f"/etc/portage/repos.conf/{name}.conf",
                             f"[{name}]\nsync-type = git\n"
                             f"sync-uri = https://old/{name}.git\n"))
    app = App()
    scr = ReposScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._repos) > 0, ticks=200)
    # inject a known enabled repo + stage an edit on it (host-independent)
    scr._repos = [Repo(name="guru", sync_type="git",
                       sync_uri="https://old/guru.git", enabled=True)]
    scr._disabled = []
    scr._pending.edit("guru", "git", "https://new/guru.git", "80")
    scr._rebuild()
    assert "*" in _render(scr)                          # staged-edit mark
    app.loop.run_until_complete(scr._accept())
    cw = captured["writes"][0]
    assert cw.path.endswith("repos.conf/guru.conf")
    assert "sync-uri = https://new/guru.git" in cw.text
    assert "priority = 80" in cw.text
    assert "https://old" not in cw.text


def test_deploy_key_screen_shows_then_generates(monkeypatch):
    from gest.tui.screens import deploykey as dk

    class _FakeSsh:
        state = {"has": False, "pub": ""}

        async def connect(self):
            return self

        async def deploy_key(self):
            s = _FakeSsh.state
            return (s["has"], s["pub"], "/root/.ssh/id_ed25519.pub")

        async def ensure_deploy_key(self):
            _FakeSsh.state = {"has": True,
                              "pub": "ssh-ed25519 AAAAKEYDATA gest-deploy@box"}
            return (True, _FakeSsh.state["pub"], "/root/.ssh/id_ed25519.pub",
                    "Generated a new deploy key.")

        async def close(self):
            return None

    _FakeSsh.state = {"has": False, "pub": ""}
    monkeypatch.setattr(dk, "SshBackend", _FakeSsh)
    app = App()
    scr = dk.DeployKeyScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: "No key yet" in _render(scr), ticks=100)
    assert "No key yet" in _render(scr)          # initial: none exists
    assert "Deploy keys" in _render(scr)          # GitHub instructions shown
    scr.keypress(_SIZE, "g")                       # generate (would prompt polkit)
    _pump(app, lambda: "ssh-ed25519" in _render(scr), ticks=100)
    assert "ssh-ed25519 AAAAKEYDATA" in _render(scr)


def test_repos_deploy_key_key_opens_screen():
    from gest.tui.screens.deploykey import DeployKeyScreen
    app = App()
    scr = ReposScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._repos) > 0, ticks=200)
    scr.keypress(_SIZE, "k")
    assert isinstance(app._stack[-1], DeployKeyScreen)


def test_focusable_actions_activate_focused():
    from gest.tui.runtime import focusable_actions
    fired = []
    row = focusable_actions([("Cancel", lambda: fired.append("c")),
                             ("OK", lambda: fired.append("ok"))])
    row.focus_position = row.button_position(1)     # focus the OK button
    assert row.activate_focused() and fired == ["ok"]


def test_repos_tab_reaches_action_buttons_and_activates():
    app = App()
    base = urwid.Text("home")
    app._stack.append(base)
    scr = ReposScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._repos) > 0, ticks=200)
    body = scr._frame.body
    body.focus_position = 0                          # the repo list
    scr.keypress(_SIZE, "tab")                       # list -> Cancel
    assert scr._on_action_row() and scr._actions.focus is scr._actions.buttons[0]
    scr.keypress(_SIZE, "tab")                       # Cancel -> Accept
    assert scr._actions.focus is scr._actions.buttons[1]
    scr.keypress(_SIZE, "tab")                       # Accept -> back to list
    assert body.focus_position == 0
    # footer switches to the action-row keys when a button is focused
    body.focus_position = 0
    scr.keypress(_SIZE, "tab")                        # onto Cancel
    assert any(lbl == "Activate" for _k, lbl in scr._footer_context())
    scr.keypress(_SIZE, "enter")                      # Cancel with no pending -> pop
    assert app._stack[-1] is base


def test_repos_arrows_stay_in_list():
    app = App()
    scr = ReposScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._repos) > 0, ticks=200)
    body = scr._frame.body
    body.focus_position = 0
    scr._walker.set_focus(len(scr._repos) - 1)        # bottom of the list
    scr.keypress(_SIZE, "down")                        # must not jump to the actions
    assert body.focus_position == 0


def test_repos_stages_changes_then_clears():
    app = App()
    scr = ReposScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._repos) > 0, ticks=200)
    idx = next((i for i, r in enumerate(scr._repos) if not r.main), None)
    if idx is None:
        pytest.skip("no non-main repository configured on this host")
    scr._walker.set_focus(idx)
    name = scr._repos[idx].name
    scr.keypress(_SIZE, "d")                 # stage disable — NOT applied
    assert scr._pending.state_of(name) == "disable"
    assert scr._pending.count() == 1
    assert "pending change" in _render(scr)  # count line, not a Change column
    scr.keypress(_SIZE, "d")                 # same key toggles the mark off
    assert scr._pending.is_empty
    scr.keypress(_SIZE, "t")                 # stage a refresh toggle
    assert not scr._pending.is_empty
    scr.keypress(_SIZE, "f9")                # F9 Cancel discards all pending
    assert scr._pending.is_empty


def test_repos_reenable_disabled_repo():
    from gest.core.repos.reader import Repo
    app = App()
    scr = ReposScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._repos) > 0, ticks=200)
    d = Repo(name="zz-disabled", sync_type="git", sync_uri="https://h/z.git",
             enabled=False)
    scr._disabled = [d]
    scr._repos = [*scr._repos, d]
    scr._rebuild()
    scr._walker.set_focus(len(scr._repos) - 1)   # focus the greyed disabled row
    scr.keypress(_SIZE, "a")                      # a re-enables a disabled repo
    assert scr._pending.state_of("zz-disabled") == "enable"
    # it stays on its own row — no spurious duplicate "new" row
    hits = [e for e in scr._entries if e and e[0] == "repo"
            and e[1].name == "zz-disabled"]
    assert len(hits) == 1
    assert sum(1 for e in scr._entries if e and e[1:] == ("zz-disabled",)) == 0
    scr.keypress(_SIZE, "a")                      # toggle the re-enable back off
    assert scr._pending.is_empty


def test_cleanup_lists_orphans_and_toggles_keep():
    app = App()
    scr = CleanupScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: scr._plan is not None, ticks=400)
    if not scr._orphans():
        pytest.skip("no orphaned packages on this host")
    assert "✓" in _render(scr)                    # marked for removal by default
    o = scr._orphans()[0]
    scr._walker.set_focus(0)
    scr.keypress(_SIZE, " ")                      # Space keeps it (unmarks)
    assert o.cp in scr._kept
    scr.keypress(_SIZE, " ")                      # toggle back to remove
    assert o.cp not in scr._kept
    scr.keypress(_SIZE, "n")                      # keep all
    assert len(scr._kept) == len(scr._orphans())
    scr.keypress(_SIZE, "a")                      # mark all for removal
    assert not scr._kept


def _world_members(monkeypatch, pkgs):
    from gest.core.software import reader
    monkeypatch.setattr(reader, "list_installed", lambda: pkgs)


def _focus_set(scr, idx):
    """Focus sidebar entry ``idx``; the walker's "modified" signal syncs members."""
    scr._focus_pane("sets")
    scr._set_walker.set_focus(idx)


def test_world_lists_members_and_marks(monkeypatch):
    from gest.core.software.model import Package
    from gest.core.software.sets import PackageSet
    from gest.tui.screens import world as W
    _world_members(monkeypatch, [
        Package(cp="app-misc/neofetch", version="7.1.0", world_member=True),
        Package(cp="dev-lang/python", version="3.11.9", world_member=True),
        Package(cp="sys-libs/glibc", version="2.39", world_member=False),
    ])
    monkeypatch.setattr(W.sets, "list_sets", lambda: [
        PackageSet(name="@system", atoms=["sys-libs/glibc"], description="Core")])
    app = App()
    scr = W.WorldScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: bool(scr._world_pkgs), ticks=200)
    assert len(scr._world_pkgs) == 2                    # dependency-only excluded
    out = _render(scr)
    assert "neofetch" in out and "python" in out        # World-set members (default)
    assert "World set" in out and "@system" in out      # sidebar lists the sets
    assert "[Cancel]" in out and "[Apply]" in out       # one unified Apply action
    scr._focus_pane("members")
    scr._walker.set_focus(0)
    scr.keypress(_SIZE, " ")                            # mark the first World-set pkg
    assert scr._marked == {"app-misc/neofetch"}
    assert "✓" in _render(scr)
    scr.keypress(_SIZE, "a")                            # mark all
    assert scr._marked == {"app-misc/neofetch", "dev-lang/python"}
    scr.keypress(_SIZE, "n")                            # unmark all
    assert not scr._marked


def test_world_sets_browser_read_only(monkeypatch):
    from gest.core.software.model import Package
    from gest.core.software.sets import PackageSet
    from gest.tui.screens import world as W
    _world_members(monkeypatch, [
        Package(cp="app-misc/neofetch", version="7.1.0", world_member=True)])
    monkeypatch.setattr(W.sets, "list_sets", lambda: [
        PackageSet(name="@system", atoms=["sys-apps/baselayout", "sys-libs/glibc"],
                   description="Core system", kind="builtin"),
    ])
    app = App()
    scr = W.WorldScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: bool(scr._sidebar), ticks=200)
    _focus_set(scr, 1)                                  # @system (builtin)
    out = _render(scr)
    assert "@system" in out and "sys-apps/baselayout" in out and "read-only" in out
    assert scr._focused_custom() is None and not scr._is_world()
    scr._apply()                                        # nothing staged → no-op
    assert _FakeSoftwareBackend.deselected == []


def test_world_deselect_commits_via_backend(monkeypatch):
    from gest.core.software.model import Package
    from gest.tui.screens import world as W
    _world_members(monkeypatch, [
        Package(cp="app-misc/neofetch", version="7.1.0", world_member=True)])
    monkeypatch.setattr(W.sets, "list_sets", lambda: [])
    app = App()
    scr = W.WorldScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: bool(scr._world_pkgs), ticks=200)
    scr._marked = {"app-misc/neofetch"}                 # staged deselect
    app.loop.run_until_complete(scr._commit())          # Apply
    assert _FakeSoftwareBackend.deselected == [["app-misc/neofetch"]]
    assert not scr._marked                              # cleared on success


def _world_with_sets(monkeypatch, app, custom):
    """A loaded WorldScreen (one world member + given custom sets) with a fake
    PortageBackend recording writes. Returns (screen, writes: [(path, text)])."""
    from gest.core.software.model import Package
    from gest.tui.screens import world as W
    _world_members(monkeypatch, [
        Package(cp="app-misc/neofetch", version="7.1", world_member=True)])
    monkeypatch.setattr(W.sets, "list_sets", lambda: list(custom))
    writes: list = []

    class _FakePortage:
        async def connect(self):
            return self

        async def write_config(self, ws):
            writes.extend((w.path, w.text) for w in ws)
            return True

        async def close(self):
            return None

    monkeypatch.setattr(W, "PortageBackend", _FakePortage)
    scr = W.WorldScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: bool(scr._sidebar), ticks=200)
    return scr, writes


def test_world_set_edit_is_staged_then_committed(monkeypatch):
    from gest.core.software.sets import PackageSet
    app = App()
    scr, writes = _world_with_sets(monkeypatch, app, [
        PackageSet(name="@media", atoms=["media-video/mpv"], kind="custom")])
    scr._stage("media", ["media-video/mpv", "x11-wm/i3"])   # add an atom (staged)
    assert scr._edits == {"media": ["media-video/mpv", "x11-wm/i3"]}
    assert writes == []                                     # nothing written yet
    assert scr._has_pending()
    app.loop.run_until_complete(scr._commit())              # Apply
    assert len(writes) == 1
    path, text = writes[0]
    assert path == "/etc/portage/sets/media"
    assert "x11-wm/i3" in text and text.startswith("# GeST")
    assert scr._edits == {}                                 # cleared after apply


def test_world_stage_delete_commits_empty(monkeypatch):
    from gest.core.software.sets import PackageSet
    app = App()
    scr, writes = _world_with_sets(monkeypatch, app, [
        PackageSet(name="@media", atoms=["media-video/mpv"], kind="custom")])
    _focus_set(scr, 1)                                      # @media
    scr._toggle_delete("media")                            # stage delete
    assert scr._edits == {"media": None}
    assert writes == []                                     # not written until Apply
    app.loop.run_until_complete(scr._commit())
    assert writes == [("/etc/portage/sets/media", "")]      # empty text = delete


def test_world_new_set_toggle_delete_cancels_it(monkeypatch):
    app = App()
    scr, _ = _world_with_sets(monkeypatch, app, [])
    scr._edits["mydesktop"] = []                            # a staged new (empty) set
    scr._populate_sidebar()
    assert scr._is_new("mydesktop")
    scr._toggle_delete("mydesktop")                        # deleting an unsaved new = cancel
    assert "mydesktop" not in scr._edits


def test_world_custom_set_keys_open_editors(monkeypatch):
    from gest.core.software.sets import PackageSet
    app = App()
    scr, _ = _world_with_sets(monkeypatch, app, [
        PackageSet(name="@media", atoms=["media-video/mpv"], kind="custom")])
    _focus_set(scr, 1)                                     # @media (custom)
    assert scr._focused_custom() == "media"
    keys = [k for k, _label in scr._footer_context()]
    assert "c" in keys and "a" in keys and "d" in keys    # create/add/delete offered
    depth = len(app._stack)
    scr.keypress(_SIZE, "a")                              # Add atom → modal overlay
    assert len(app._stack) == depth + 1
    assert isinstance(app._stack[-1], urwid.Overlay)
    app.pop()
    scr.keypress(_SIZE, "c")                              # New set → modal overlay
    assert isinstance(app._stack[-1], urwid.Overlay)


def test_world_apply_with_nothing_pending_is_noop(monkeypatch):
    app = App()
    scr, writes = _world_with_sets(monkeypatch, app, [])
    scr._apply()
    assert writes == [] and _FakeSoftwareBackend.deselected == []


def test_update_screen_lists_changes(monkeypatch):
    from gest.core.software import update as core_update
    from gest.core.software.update import Change, UpdatePlan
    from gest.tui.screens.update import UpdateScreen
    fake = UpdatePlan(changes=[
        Change("app-arch/gzip", "1.13", "1.14", "update", False, 430080),
        Change("dev-libs/newdep", "", "2.0", "new", False, 1258291),
    ], ok=True)
    monkeypatch.setattr(core_update, "plan_update", lambda: fake)
    app = App()
    scr = UpdateScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: scr._plan is not None, ticks=200)
    out = _render(scr)
    assert "gzip" in out and "1.13 → 1.14" in out and "newdep" in out
    assert "Updates 1" in out and "New 1" in out


def test_update_screen_empty_state(monkeypatch):
    from gest.core.software import update as core_update
    from gest.tui.screens.update import UpdateScreen
    monkeypatch.setattr(core_update, "plan_update",
                        lambda: core_update.UpdatePlan(changes=[], ok=True))
    app = App()
    scr = UpdateScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: scr._plan is not None, ticks=200)
    assert "up to date" in _render(scr)


def _update_with_changes(monkeypatch, app, mode="timer"):
    """An UpdateScreen scanned to one change in ``mode``; ``_update`` is spied."""
    from gest.core.software import update as core_update
    from gest.core.software.update import Change, UpdatePlan
    from gest.tui.screens.update import UpdateScreen
    fake = UpdatePlan(changes=[
        Change("app-arch/gzip", "1.13", "1.14", "update", False, 430080)], ok=True)
    monkeypatch.setattr(core_update, "plan_update", lambda: fake)
    monkeypatch.setattr("gest.core.prefs.accept_mode", lambda *a, **k: mode)
    updated: list = []
    monkeypatch.setattr(UpdateScreen, "_update", lambda self: updated.append(True))
    scr = UpdateScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: scr._armed, ticks=300)
    return scr, updated


def test_update_arms_timer_and_enter_updates(monkeypatch):
    app = App()
    app._stack.append(urwid.Text("menu"))
    scr, updated = _update_with_changes(monkeypatch, app, mode="timer")
    assert scr._timer_running                        # countdown armed after scan
    assert ("Enter", "Update now") in scr._footer_context()
    scr.keypress(_SIZE, "enter")                     # bypass → update now
    assert updated == [True] and not scr._timer_running


def test_update_esc_stops_timer_without_leaving(monkeypatch):
    app = App()
    caller = urwid.Text("menu")
    app._stack.append(caller)
    scr, updated = _update_with_changes(monkeypatch, app, mode="timer")
    scr.keypress(_SIZE, "esc")                       # first Esc: stop the countdown
    assert not scr._timer_running and updated == []
    assert app._stack[-1] is scr                     # stays on System Update
    scr.keypress(_SIZE, "esc")                       # second Esc: back to menu
    assert app._stack[-1] is caller


def test_update_immediate_mode_updates_at_once(monkeypatch):
    app = App()
    app._stack.append(urwid.Text("menu"))
    scr, updated = _update_with_changes(monkeypatch, app, mode="immediate")
    assert updated == [True] and not scr._timer_running


def test_sync_screen_lists_repos_and_tracks_progress():
    from gest.tui.screens.sync import SyncScreen
    app = App()
    scr = SyncScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: scr._repos, ticks=200)   # reads repos.conf
    if not scr._repos:
        pytest.skip("no syncable repositories on this host")
    name = scr._repos[0].name
    scr._consume(f">>> Syncing repository '{name}' into '/x'...")
    assert scr._by_name[name].status == "syncing"
    scr._consume(f"Action: sync for repo: {name}, returned code = 0")
    assert scr._by_name[name].status == "synced"
    assert "✓" in _render(scr)
    scr._finish(0, "")
    assert scr._done and not scr._running


def test_accept_run_screen_tracks_install_and_remove():
    from gest.tui.screens.accept import AcceptRunScreen
    app = App()
    scr = AcceptRunScreen(app, installs=["app-editors/vim"],
                          removes=["app-arch/oldpkg"])
    app._stack.append(scr)
    scr._consume(">>> Emerging (1 of 1) app-editors/vim-9.1::gentoo")
    assert scr._install["app-editors/vim"].status == "active"
    scr._consume(">>> Installing (1 of 1) app-editors/vim-9.1::gentoo")
    assert scr._install["app-editors/vim"].status == "done"
    scr._consume(">>> Unmerging (1 of 1) app-arch/oldpkg-1.0...")
    assert scr._remove["app-arch/oldpkg"].status == "active"
    assert "install 9.1" in _render(scr) and "remove" in _render(scr)
    scr._finish(0)                            # emerge exited 0
    assert all(it.status == "done" for it in scr._items)
    assert scr._done


def test_accept_removal_hands_straight_to_cleanup_when_orphans(monkeypatch):
    from gest.core.software.cleanup import CleanupPlan, Orphan
    from gest.tui.screens import accept as accept_mod
    from gest.tui.screens.accept import AcceptRunScreen
    plan = CleanupPlan(orphans=[Orphan("dev-libs/orphanlib", "1.0", 0)], ok=True)
    monkeypatch.setattr(accept_mod, "plan_cleanup", lambda: plan)
    app = App()
    app._stack.append(urwid.Text("software list"))
    scr = AcceptRunScreen(app, removes=["app-arch/oldpkg"])
    app._stack.append(scr)
    scr._finish(0)                            # successful removal → scan then swap
    _pump(app, lambda: isinstance(app._stack[-1], CleanupScreen))
    top = app._stack[-1]
    assert isinstance(top, CleanupScreen) and top._preloaded
    # the finished removal screen was swapped out, not left underneath
    assert not any(isinstance(w, AcceptRunScreen) for w in app._stack)
    assert "orphanlib" in _render(top)


def test_accept_removal_shows_all_clear_when_no_orphans(monkeypatch):
    from gest.core.software.cleanup import CleanupPlan
    from gest.tui.screens import accept as accept_mod
    from gest.tui.screens.accept import AcceptRunScreen
    monkeypatch.setattr(accept_mod, "plan_cleanup",
                        lambda: CleanupPlan(orphans=[], ok=True))
    app = App()
    app._stack.append(urwid.Text("software list"))
    scr = AcceptRunScreen(app, removes=["app-arch/oldpkg"])
    app._stack.append(scr)
    scr._finish(0)
    _pump(app, lambda: isinstance(app._stack[-1], urwid.Overlay))
    assert "orphaned dependencies" in _render(app._stack[-1]).lower()


def test_accept_install_only_skips_housekeeping():
    from gest.tui.screens.accept import AcceptRunScreen
    app = App()
    app._stack.append(urwid.Text("software list"))
    scr = AcceptRunScreen(app, installs=["app-editors/vim"])
    app._stack.append(scr)
    scr._finish(0)                            # install-only → result modal at once
    assert isinstance(app._stack[-1], urwid.Overlay)   # no scan, no swap


def test_run_screen_result_modal_offers_main_menu():
    from gest.tui.screens.accept import AcceptRunScreen
    app = App()
    app._stack.append(urwid.Text("main menu"))
    app._stack.append(urwid.Text("software list"))
    scr = AcceptRunScreen(app, installs=["app-editors/vim"])
    app._stack.append(scr)
    scr._finish(0)                            # install complete → result modal
    out = _render(app._stack[-1])
    assert "Back" in out and "View log" in out and "Main menu" in out
    # Main menu pops everything back to the root
    app.pop()                                 # the modal
    app.pop_to_root()
    assert len(app._stack) == 1


def test_cleanup_screen_accepts_preloaded_plan_without_rescanning():
    from gest.core.software.cleanup import CleanupPlan, Orphan
    plan = CleanupPlan(orphans=[Orphan("dev-libs/orphanlib", "1.2", 4096)],
                       counts={"to_remove": 1}, ok=True)
    app = App()
    scr = CleanupScreen(app, plan)
    assert scr._plan is plan and scr._preloaded
    assert "orphanlib" in _render(scr)


def test_app_pop_to_and_pop_to_root():
    app = App()
    a, b, c, d = (urwid.Text(x) for x in "abcd")
    for w in (a, b, c, d):
        app._stack.append(w)
    app.pop_to(b)                             # pop c, d
    assert app._stack[-1] is b and len(app._stack) == 2
    app.pop_to_root()                         # back to the root only
    assert app._stack == [a]


def test_cleanup_run_screen_offers_destinations_in_housekeeping():
    from gest.core.software.cleanup import Orphan
    from gest.tui.screens.apply import depclean_plan
    from gest.tui.screens.cleanup import CleanupRunScreen
    app = App()
    app._stack.append(urwid.Text("main menu"))
    pm = urwid.Text("package manager")
    app._stack.append(pm)
    scr = CleanupRunScreen(app, [Orphan("dev-libs/orphan", "1.0", 0)],
                           depclean_plan(), return_to=pm)
    app._stack.append(scr)
    scr._finish(0)                            # cleanup complete → destination prompt
    top = app._stack[-1]
    assert isinstance(top, urwid.Overlay)     # the completion modal
    out = _render(top)
    assert "Package Manager" in out and "View logs" in out and "Main menu" in out
    # Esc re-offers the choices rather than dropping back to the review
    scr._result = ("Completed", True, "done")
    assert scr.handle_key("esc") is None


def test_cleanup_run_screen_menu_launched_keeps_plain_result_modal():
    from gest.core.software.cleanup import Orphan
    from gest.tui.screens.apply import depclean_plan
    from gest.tui.screens.cleanup import CleanupRunScreen
    app = App()
    app._stack.append(urwid.Text("menu"))
    scr = CleanupRunScreen(app, [Orphan("dev-libs/orphan", "1.0", 0)],
                           depclean_plan())    # no return_to → menu flow
    app._stack.append(scr)
    scr._finish(0)
    out = _render(app._stack[-1])
    assert "Back" in out and "Package Manager" not in out


def test_update_run_screen_tracks_progress():
    from gest.core.software.update import Change
    from gest.tui.screens.apply import world_plan
    from gest.tui.screens.update import UpdateRunScreen
    app = App()
    changes = [Change("app-arch/gzip", "1.13", "1.14", "update", False, 1000),
               Change("dev-libs/newdep", "", "2.0", "new", False, 500)]
    # constructing schedules _run() but without pumping it never runs (no real emerge)
    scr = UpdateRunScreen(app, changes, world_plan())
    app._stack.append(scr)
    scr._consume(">>> Emerging (1 of 2) app-arch/gzip-1.14::gentoo")
    assert scr._by_cp["app-arch/gzip"].status == "building"
    scr._consume(">>> Installing (1 of 2) app-arch/gzip-1.14::gentoo")
    assert scr._by_cp["app-arch/gzip"].status == "installed"
    assert "▸" in _render(scr) or "✓" in _render(scr)
    scr._finish(0)                           # emerge exited 0
    assert all(it.status == "installed" for it in scr._items)
    assert scr._done


def test_cleanup_run_screen_tracks_removal_progress():
    from gest.core.software.cleanup import Orphan
    from gest.tui.screens.apply import depclean_plan
    from gest.tui.screens.cleanup import CleanupRunScreen
    app = App()
    orphans = [Orphan("app-arch/innoextract", "1.10-r1", 1000),
               Orphan("dev-libs/oldlib", "1.4.2", 500)]
    # Constructing schedules _run(), but without pumping the loop it never
    # executes — so no real emerge --depclean is triggered by this test.
    scr = CleanupRunScreen(app, orphans, depclean_plan())
    app._stack.append(scr)

    scr._consume(">>> Unmerging (1 of 2) app-arch/innoextract-1.10-r1...")
    assert scr._by_pf["app-arch/innoextract-1.10-r1"].status == "removing"
    scr._consume(">>> Unmerging (2 of 2) dev-libs/oldlib-1.4.2...")
    # the previous package flips to removed when the next Unmerging arrives
    assert scr._by_pf["app-arch/innoextract-1.10-r1"].status == "removed"
    assert scr._by_pf["dev-libs/oldlib-1.4.2"].status == "removing"
    assert "▸" in _render(scr) and "✓" in _render(scr)

    scr._finish(0)                              # emerge exited 0
    assert all(ln.status == "removed" for ln in scr._items)
    assert scr._done


def test_menu_launches_repos():
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    menu.keypress(_SIZE, "enter")          # Software category, focus modules
    menu.keypress(_SIZE, "down")           # Software Management -> World & Package Sets
    menu.keypress(_SIZE, "down")           # -> Software Repositories
    menu.keypress(_SIZE, "enter")
    assert isinstance(app._stack[-1], ReposScreen)


def test_preferences_lives_under_software():
    from gest.tui.screens.menu import CATEGORIES
    from gest.tui.screens.preferences import PreferencesScreen
    by_cat = {cat: [k for k, _label, _impl in mods] for cat, mods in CATEGORIES}
    assert "prefs" in by_cat["Software"]                 # software-scoped setting
    assert "prefs" not in by_cat["Miscellaneous"]        # not a global bucket
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    menu.keypress(_SIZE, "enter")                        # into Software modules
    for _ in range(by_cat["Software"].index("prefs")):
        menu.keypress(_SIZE, "down")                     # walk down to Preferences
    menu.keypress(_SIZE, "enter")
    assert isinstance(app._stack[-1], PreferencesScreen)
