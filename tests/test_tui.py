"""Headless tests for the urwid frontend (drive widgets directly).

These need urwid + a live Portage news source, so they run in the full local
suite rather than the dependency-light CI subset.
"""

import asyncio

import urwid

from gest.tui.runtime import App, Screen, ansi_markup, function_bar, strip_ansi
from gest.tui.screens.apply import ApplyScreen
from gest.tui.screens.bootloader import BootloaderScreen
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
    assert "[Help]" in out and "[Run]" in out and "[Quit]" in out
    assert "Software" in out and "Software Management" in out  # both panes
    menu.keypress(_SIZE, "down")         # move to the System category
    out2 = _render(menu)
    assert "Hostname" in out2 and "Timezone" in out2


def test_quit_is_top_level_only():
    import pytest
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
    for _ in range(4):
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


def test_software_accept_opens_apply_screen():
    app = App()
    scr = _software(app)
    scr.keypress(_SIZE, "tab")    # focus table
    scr.keypress(_SIZE, " ")      # mark one
    scr.keypress(_SIZE, "f10")    # Accept
    assert isinstance(app._stack[-1], ApplyScreen)


def test_menu_launches_software():
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    menu.keypress(_SIZE, "enter")  # Software category -> modules (Software Mgmt first)
    menu.keypress(_SIZE, "enter")  # launch
    assert isinstance(app._stack[-1], SoftwareScreen)


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


def test_menu_launches_repos():
    app = App()
    menu = MenuScreen(app)
    app._stack.append(menu)
    menu.keypress(_SIZE, "enter")          # Software category, focus modules
    for _ in range(5):
        menu.keypress(_SIZE, "down")       # ...news -> repositories (6th item)
    menu.keypress(_SIZE, "enter")
    assert isinstance(app._stack[-1], ReposScreen)
