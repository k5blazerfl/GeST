"""Headless tests for the urwid frontend (drive widgets directly).

These need urwid + a live Portage news source, so they run in the full local
suite rather than the dependency-light CI subset.
"""

import asyncio

from gest.uwui.runtime import App, Screen, function_bar
from gest.uwui.screens.menu import MenuScreen
from gest.uwui.screens.news import NewsScreen

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
