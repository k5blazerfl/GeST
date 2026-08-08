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
from gest.tui.screens.eselect import EselectScreen
from gest.tui.screens.makeconf import MakeconfScreen
from gest.tui.screens.menu import MenuScreen
from gest.tui.screens.network import NetworkScreen
from gest.tui.screens.news import NewsScreen
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
    assert "Categories" in out and "Modules" in out
    assert "Software Management" in out  # Software category's modules by default
    menu.keypress(_SIZE, "down")         # move to the System category
    out2 = _render(menu)
    assert "Hostname" in out2 and "Timezone" in out2


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


def test_users_list_and_group_toggle():
    app = App()
    scr = UsersScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._order) > 0)
    assert scr._order and scr._view == "users"
    assert "root" in _render(scr)
    scr.keypress(_SIZE, "g")
    _pump(app, lambda: scr._view == "groups" and len(scr._order) > 0)
    assert "Groups" in _render(scr)


def test_users_add_modal_opens_and_cancels():
    app = App()
    scr = UsersScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._order) > 0)
    scr.keypress(_SIZE, "a")
    assert isinstance(app._stack[-1], urwid.Overlay)
    assert "Add user" in _render(app._stack[-1])
    app._stack[-1].keypress(_SIZE, "esc")
    assert isinstance(app._stack[-1], UsersScreen)


def test_users_edit_modal_prefills():
    app = App()
    scr = UsersScreen(app)
    app._stack.append(scr)
    _pump(app, lambda: len(scr._order) > 0)
    scr.keypress(_SIZE, "e")
    assert "Edit user" in _render(app._stack[-1])


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


def test_software_loads_marks_and_clears():
    app = App()
    scr = _software(app)
    assert scr._cps  # installed packages
    scr.keypress(_SIZE, "down")   # search -> checkboxes
    scr.keypress(_SIZE, "down")   # -> table
    assert scr._pile.focus_position == scr._TABLE_IDX
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
    scr._pile.focus_position = 0
    scr._search.set_edit_text("app-editors/vim")
    scr.keypress(_SIZE, "enter")
    _pump(app, lambda: 0 < len(scr._cps) < installed, ticks=300)
    assert any("vim" in cp for cp in scr._cps)


def test_software_accept_opens_apply_screen():
    app = App()
    scr = _software(app)
    scr.keypress(_SIZE, "down")
    scr.keypress(_SIZE, "down")
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
    scr.keypress(_SIZE, "down")
    scr.keypress(_SIZE, "down")   # focus table
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
